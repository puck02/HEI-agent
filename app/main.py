"""
hel-agent — FastAPI application entrypoint.

AI Health Agent Backend for HElDairy.
Demo version: SQLite + DeepSeek, no external dependencies.
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
        log.info("qdrant_skipped", reason="demo_mode")

    # Init LLM Router
    from app.llm.router import get_llm_router
    router = get_llm_router()
    log.info("llm_router_ready", providers=[p["name"] for p in router.get_status()])

    yield

    # ── Shutdown ─────────────────────────────────────────
    log.info("shutting_down")

    # Close Redis/short-term memory (skip if not configured)
    if settings.redis_url:
        try:
            from app.memory.short_term import get_short_term_memory
            await get_short_term_memory().close()
        except Exception:
            pass

    # Close notification queue (skip in demo)
    if not settings.demo_mode:
        try:
            from app.notifications.queue import get_notification_queue
            await get_notification_queue().close()
        except Exception:
            pass

    # Close FCM (skip in demo)
    if not settings.demo_mode and settings.fcm_service_account_json:
        try:
            from app.push.fcm import get_push_service
            await get_push_service().close()
        except Exception:
            pass

    # Close Qdrant (skip in demo)
    if not settings.demo_mode and settings.qdrant_url:
        try:
            from app.rag.engine import get_rag_engine
            await get_rag_engine().close()
        except Exception:
            pass


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="HEl Agent API",
        description="AI Health Agent Backend — Multi-Agent with LLM Router, RAG, Reflection (Demo Mode)",
        version="0.2.0-demo",
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

    # Optional routers (may have external dependencies)
    try:
        from app.api.v1.medication import router as medication_router
        app.include_router(medication_router, prefix="/api/v1")
    except Exception as e:
        log.warning("medication_router_skipped", error=str(e))

    if not settings.demo_mode:
        try:
            from app.api.v1.sync import router as sync_router
            app.include_router(sync_router, prefix="/api/v1")
        except Exception as e:
            log.warning("sync_router_skipped", error=str(e))

    # ── Health Check ─────────────────────────────────────
    @app.get("/health", tags=["system"])
    async def health_check():
        from app.llm.router import get_llm_router
        router = get_llm_router()
        return {
            "status": "ok",
            "app": settings.app_name,
            "env": settings.app_env,
            "demo_mode": settings.demo_mode,
            "database": settings.database_type,
            "llm_providers": router.get_status(),
        }

    @app.get("/", tags=["system"])
    async def root():
        return {
            "name": "HEl Agent API",
            "version": "0.2.0-demo",
            "docs": "/docs",
            "demo_mode": settings.demo_mode,
            "features": [
                "Pipeline Architecture (FastPipeline + AgentPipeline)",
                "RAGDecider (3-layer strategy)",
                "ReflectionPolicy (pluggable scoring)",
                "Multi-Provider LLM Router",
            ],
        }

    # ── Demo Chat (no auth required) ───────────────────
    @app.post("/api/demo/chat", tags=["demo"])
    async def demo_chat(request: Request):
        """Demo chat endpoint — no authentication required."""
        from app.llm.router import get_llm_router
        from app.rag.decider import RAGDecider
        from app.agents.router import IntentRouter
        from app.memory.session_store import get_session_store
        
        body = await request.json()
        message = body.get("message", "")
        session_id = body.get("session_id")
        
        if not message:
            return {"error": "message is required"}
        
        router = get_llm_router()
        intent_router = IntentRouter()
        rag_decider = RAGDecider()
        
        # Classify intent
        intent = await intent_router.classify_intent(message)
        
        # Check if RAG is needed
        need_rag = await rag_decider.should_retrieve(message, intent)
        
        # Inject RAG context if needed
        rag_context = ""
        references: list[dict] = []
        if need_rag:
            from app.rag.engine import get_rag_engine
            rag_engine = get_rag_engine()
            rag_context, references = await rag_engine.retrieve_with_refs(
                query=message,
                top_k=3,
            )
            if rag_context:
                log.info("demo_rag_injected", query=message[:50], refs=len(references))
        
        # Build system prompt
        system_prompt = "你是「Kitty 健康管家 🎀」，一个专业的 AI 私人健康医生。请用温暖、专业的语气回答用户问题。"
        if rag_context:
            system_prompt += f"\n\n请参考以下知识库内容回答，并在回答中引用相关知识：\n{rag_context}"
        
        # Generate response
        result = await router.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            temperature=0.7,
            max_tokens=500,
        )
        
        # Save messages to session if session_id provided
        if session_id:
            store = get_session_store()
            store.add_message(session_id, "user", message)
            store.add_message(session_id, "assistant", result.content)
        
        return {
            "response": result.content,
            "intent": intent,
            "need_rag": need_rag,
            "references": references,
            "provider": result.provider,
            "model": result.model,
            "latency_ms": round(result.latency_ms, 1),
            "tokens": result.usage,
        }

    return app


# Uvicorn entrypoint
app = create_app()
