"""
hel-agent — FastAPI application entrypoint.

AI Health Agent Backend for HElDairy.
"""

from __future__ import annotations

import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    settings = get_settings()

    # ── Startup ──────────────────────────────────────────
    log.info("starting", app=settings.app_name, env=settings.app_env)

    # Init database tables (dev mode only — use Alembic in production)
    if settings.debug:
        from app.database import init_db
        try:
            await init_db()
            log.info("database_initialized")
        except Exception as e:
            log.warning("database_init_failed", error=str(e))

    # Ensure Qdrant collections
    try:
        from app.rag.engine import get_rag_engine
        rag = get_rag_engine()
        await rag.ensure_collections()
        log.info("qdrant_collections_ready")
    except Exception as e:
        log.warning("qdrant_init_failed", error=str(e))

    # Init LLM Router
    from app.llm.router import get_llm_router
    router = get_llm_router()
    log.info("llm_router_ready", providers=[p["name"] for p in router.get_status()])

    yield

    # ── Shutdown ─────────────────────────────────────────
    log.info("shutting_down")

    try:
        from app.memory.short_term import get_short_term_memory
        await get_short_term_memory().close()
    except Exception:
        pass

    try:
        from app.rag.engine import get_rag_engine
        await get_rag_engine().close()
    except Exception:
        pass


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="HEl Agent API",
        description="AI Health Agent Backend for HElDairy — Multi-Agent system with LLM Router, RAG, Memory, MCP Tools",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # ── CORS ─────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ───────────────────────────────────────────
    from app.auth.router import router as auth_router
    from app.api.v1.chat import router as chat_router
    from app.api.v1.health import router as health_router
    from app.api.v1.medication import router as medication_router
    from app.api.v1.sync import router as sync_router

    app.include_router(auth_router)
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(medication_router, prefix="/api/v1")
    app.include_router(sync_router, prefix="/api/v1")

    # ── Health Check ─────────────────────────────────────
    @app.get("/health", tags=["system"])
    async def health_check():
        from app.llm.router import get_llm_router
        router = get_llm_router()
        return {
            "status": "ok",
            "app": settings.app_name,
            "env": settings.app_env,
            "llm_providers": router.get_status(),
        }

    @app.get("/", tags=["system"])
    async def root():
        return {
            "name": "HEl Agent API",
            "version": "0.1.0",
            "docs": "/docs",
        }

    return app


# Uvicorn entrypoint
app = create_app()
