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
    @app.post("/api/demo/chat", tags=["demo"])
    async def demo_chat(request: Request):
        """Demo chat endpoint — no authentication required."""
        body = await request.json()
        message = body.get("message", "")
        session_id = body.get("session_id", "demo_session")
        
        from app.agent.chat_agent import ChatAgent
        agent = ChatAgent()
        result = await agent.chat(
            user_id="demo_user",
            session_id=session_id or "demo_session",
            message=message,
            single_round=True,
        )
        return {
            "response": result["answer"],
            "answer": result["answer"],
            "session_id": session_id or "demo_session",
            "tool_calls_made": result.get("tool_calls_made", []),
            "latency_ms": result.get("latency_ms", 0),
            "references": [],
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
