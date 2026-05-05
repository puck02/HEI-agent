"""
hel-agent — FastAPI application entrypoint.

AI Health Agent Backend for HElDairy.
Naive Agent Mode: single ChatAgent with ReAct + Tools architecture.
"""

from __future__ import annotations

import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import DBAPIError

from app.config import get_settings

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    settings = get_settings()

    # ── Startup ──────────────────────────────────────────
    log.info("starting", app=settings.app_name, env=settings.app_env, demo=settings.demo_mode)

    # Verify DB connectivity early to fail fast on bad runtime config
    try:
        from app.database import check_db_connection
        await check_db_connection()
        log.info("database_connected", type=settings.database_type)
    except Exception as e:
        log.warning("database_connect_failed", error=str(e))

    # Init database tables (dev mode only — use Alembic in production)
    if settings.debug:
        from app.database import init_db
        try:
            await init_db()
            log.info("database_initialized")
        except Exception as e:
            log.warning("database_init_failed", error=str(e))

    # Ensure daily_reports table (raw SQL to avoid mapper conflicts)
    try:
        from app.database import engine
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS daily_reports ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  user_id TEXT NOT NULL,"
                "  report_date DATE NOT NULL,"
                "  answers TEXT NOT NULL,"
                "  advice TEXT NOT NULL,"
                "  created_at DATETIME DEFAULT (datetime('now'))"
                ")"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_daily_reports_user_date "
                "ON daily_reports (user_id, report_date)"
            ))
        log.info("daily_reports_table_ready")
    except Exception as e:
        log.warning("daily_reports_table_init_failed", error=str(e))

    # Ensure Qdrant collections (use when QDRANT_URL is set, regardless of mode)
    if settings.qdrant_url:
        try:
            from app.rag.engine import get_rag_engine
            rag = get_rag_engine()
            await rag.ensure_collections()
            log.info("qdrant_collections_ready")
        except Exception as e:
            log.warning("qdrant_init_failed", error=str(e))
    else:
        log.info("qdrant_skipped", reason="no_qdrant_url")

    # Init LLM Router
    from app.llm.router import get_llm_router
    router = get_llm_router()
    log.info("llm_router_ready", providers=[p["name"] for p in router.get_status()])

    yield

    # ── Shutdown ─────────────────────────────────────────
    log.info("shutting_down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="HEl Agent API",
        description="AI Health Agent Backend — Naive Agent Mode with ReAct + Tools",
        version="0.3.0-naive",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ─────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DBAPIError)
    async def db_exception_handler(request: Request, exc: DBAPIError):
        log.error("db_request_failed", path=request.url.path, method=request.method, error=str(exc))
        return JSONResponse(
            status_code=503,
            content={"detail": "数据库暂时不可用，请稍后重试", "error": "database_unavailable"},
        )

    @app.exception_handler(ConnectionError)
    async def connection_exception_handler(request: Request, exc: ConnectionError):
        log.error("connection_request_failed", path=request.url.path, method=request.method, error=str(exc))
        return JSONResponse(
            status_code=503,
            content={"detail": "服务连接暂时不可用，请稍后重试", "error": "connection_unavailable"},
        )

    # ── Routes ───────────────────────────────────────────
    from app.auth.router import router as auth_router
    from app.api.v1.chat import router as chat_router
    from app.api.v1.completion import router as completion_router
    from app.api.v1.health import router as health_router
    from app.api.v1.sessions import router as sessions_router

    app.include_router(auth_router)
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(completion_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(sessions_router, prefix="/api/v1")

    # Medication router
    try:
        from app.api.v1.medication import router as medication_router
        app.include_router(medication_router, prefix="/api/v1")
    except Exception as e:
        log.warning("medication_router_skipped", error=str(e))

    # ── Demo Chat (no auth) ──────────────────────────────
    # Singleton ChatAgent so tool confirmation pending state persists across requests
    _demo_chat_agent: "ChatAgent | None" = None

    def _get_demo_chat_agent() -> "ChatAgent":
        nonlocal _demo_chat_agent
        if _demo_chat_agent is None:
            from app.agent.chat_agent import ChatAgent
            _demo_chat_agent = ChatAgent()
        return _demo_chat_agent

    @app.post("/api/demo/chat", tags=["demo"])
    async def demo_chat(request: Request):
        """Demo chat endpoint — no authentication required."""
        body = await request.json()
        message = body.get("message", "")
        session_id = body.get("session_id", "demo_session")

        from app.agent.chat_agent import ChatAgent
        from app.memory.session_store import get_session_store

        store = get_session_store()

        # Auto-create session if it doesn't exist yet
        if not store.get_session(session_id):
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            store._sessions[session_id] = {
                "session_id": session_id,
                "title": "新对话",
                "created_at": now,
                "updated_at": now,
                "messages": [],
            }

        # Get conversation history from session store
        raw_history = store.get_messages(session_id)
        conversation_history = [
            {"role": m["role"], "content": m["content"]}
            for m in raw_history
        ]

        # Save user message to session
        store.add_message(session_id, "user", message)

        agent = _get_demo_chat_agent()
        result = await agent.chat(
            user_id="demo_user",
            session_id=session_id or "demo_session",
            message=message,
            conversation_history=conversation_history,
            single_round=False,
        )

        # Save assistant response to session
        answer_text = result.get("answer", "")
        if answer_text:
            store.add_message(session_id, "assistant", answer_text)

        return {
            "response": answer_text,
            "answer": answer_text,
            "session_id": session_id or "demo_session",
            "tool_calls_made": result.get("tool_calls_made", []),
            "latency_ms": result.get("latency_ms", 0),
            "references": [],
        }

    # ── Demo Medication API (no auth) ────────────────────
    @app.get("/api/demo/medications", tags=["demo"])
    async def get_demo_medications(user_id: str = "demo_user"):
        """Get all medications for demo user."""
        from app.services.medication_service import MedicationService
        try:
            service = MedicationService()
            records = service.get_all(user_id)
            return {"medications": records}
        except Exception as e:
            return {"medications": [], "error": str(e)}

    @app.post("/api/demo/medications", tags=["demo"])
    async def add_demo_medication(request: Request):
        """Add a medication for demo user."""
        body = await request.json()
        user_id = body.get("user_id", "demo_user")
        from app.services.medication_service import MedicationService
        try:
            service = MedicationService()
            med_id = service.add(user_id, {
                "name": body.get("name", ""),
                "dosage": body.get("dosage", ""),
                "frequency": body.get("frequency", ""),
                "notes": body.get("notes", ""),
            })
            return {"ok": True, "id": med_id}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Daily Report (one per user per day) ───────────────
    @app.get("/api/demo/daily-report", tags=["demo"])
    async def get_daily_report(user_id: str = "demo_user"):
        """Get today's daily report if it exists."""
        from datetime import date
        from app.database import engine
        from sqlalchemy import text

        today = date.today()
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT * FROM daily_reports WHERE user_id = :uid AND report_date = :d"),
                {"uid": user_id, "d": today.isoformat()},
            )
            row = result.fetchone()

        if row is None:
            return {"exists": False, "report": None}

        import json
        return {
            "exists": True,
            "report": {
                "id": row.id,
                "user_id": row.user_id,
                "report_date": str(row.report_date),
                "answers": json.loads(row.answers),
                "advice": row.advice,
                "created_at": str(row.created_at) if row.created_at else None,
            },
        }

    @app.post("/api/demo/daily-report", tags=["demo"])
    async def save_daily_report(request: Request):
        """Save today's daily report (upsert)."""
        from datetime import date
        from app.database import engine
        from sqlalchemy import text
        import json

        body = await request.json()
        user_id = body.get("user_id", "demo_user")
        answers = body.get("answers", {})
        advice = body.get("advice", "")

        today = date.today()
        answers_json = json.dumps(answers, ensure_ascii=False)

        async with engine.connect() as conn:
            # Upsert: check if today's report exists
            result = await conn.execute(
                text("SELECT id FROM daily_reports WHERE user_id = :uid AND report_date = :d"),
                {"uid": user_id, "d": today.isoformat()},
            )
            existing = result.fetchone()

            if existing:
                await conn.execute(
                    text("UPDATE daily_reports SET answers = :a, advice = :adv WHERE id = :id"),
                    {"a": answers_json, "adv": advice, "id": existing.id},
                )
                report_id = existing.id
            else:
                result = await conn.execute(
                    text(
                        "INSERT INTO daily_reports (user_id, report_date, answers, advice, created_at) "
                        "VALUES (:uid, :d, :a, :adv, datetime('now')) RETURNING id, user_id, report_date, answers, advice"
                    ),
                    {"uid": user_id, "d": today.isoformat(), "a": answers_json, "adv": advice},
                )
                row = result.fetchone()
                report_id = row.id

            await conn.commit()

        return {
            "ok": True,
            "report": {
                "id": report_id,
                "user_id": user_id,
                "report_date": str(today),
                "answers": answers,
                "advice": advice,
            },
        }

    # ── Health Check ─────────────────────────────────────
    @app.get("/health", tags=["system"])
    async def health_check():
        from app.llm.router import get_llm_router
        router = get_llm_router()
        return {
            "status": "ok",
            "app": settings.app_name,
            "env": settings.app_env,
            "mode": "naive-agent",
            "demo_mode": settings.demo_mode,
            "database": settings.database_type,
            "llm_providers": router.get_status(),
        }

    @app.get("/", tags=["system"])
    async def root():
        return {
            "name": "HEl Agent API",
            "version": "0.3.0-naive",
            "docs": "/docs",
            "demo_mode": settings.demo_mode,
            "architecture": "Naive Agent Mode — ReAct + Tools",
            "features": [
                "ChatAgent (ReAct while-loop)",
                "12 AI Tools (7 read + 5 write)",
                "Hybrid Memory (Qdrant + BM25 + RRF + Rerank)",
                "Service Layer (single data entry point)",
                "LLM Router with auto-failover",
            ],
        }

    return app


# Uvicorn entrypoint
app = create_app()
