"""
Application configuration — loads from .env via pydantic-settings.

Demo version: supports SQLite for lightweight deployment.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────
    app_name: str = "hel-agent"
    app_env: str = "development"
    debug: bool = True

    # ── Server ───────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    # ── Database ─────────────────────────────────────────
    # "sqlite" for demo, "postgresql" for production
    database_type: str = "sqlite"
    database_url: str = "sqlite+aiosqlite:///./hei_agent.db"
    database_url_sync: str = "sqlite:///./hei_agent.db"

    # ── Redis (optional for demo) ────────────────────────
    redis_url: str = ""

    # ── Qdrant (optional for demo) ───────────────────────
    qdrant_url: str = ""
    qdrant_api_key: Optional[str] = None

    # ── JWT ──────────────────────────────────────────────
    jwt_secret_key: str = "demo-secret-key-for-testing-only"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24h
    jwt_refresh_token_expire_days: int = 30

    # ── LLM Providers ───────────────────────────────────
    deepseek_api_key: Optional[str] = None
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    glm_api_key: Optional[str] = None
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    glm_model: str = "glm-4-flash"

    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"

    dashscope_api_key: Optional[str] = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_request_timeout_seconds: float = 22.0
    chat_pipeline_timeout_seconds: float = 28.0
    chat_inference_timeout_seconds: float = 16.0
    chat_history_max_messages: int = 6
    chat_history_max_chars: int = 1200

    # ── Embedding ────────────────────────────────────────
    embedding_provider: str = "dashscope"
    embedding_model: str = "text-embedding-v4"

    # ── RAG ──────────────────────────────────────────────
    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 200
    rag_top_k: int = 5
    rag_rerank_top_k: int = 20
    rag_query_rewrite_enabled: bool = True

    # ── Memory ───────────────────────────────────────────
    short_term_memory_ttl: int = 86400  # 24h seconds
    short_term_memory_max_turns: int = 20
    long_term_memory_decay_rate: float = 0.95

    # ── MCP Tools ────────────────────────────────────────
    weather_api_key: Optional[str] = None
    search_api_key: Optional[str] = None

    # ── Push (FCM) — disabled for demo ───────────────────
    fcm_service_account_json: Optional[str] = None

    # ── Demo mode ────────────────────────────────────────
    demo_mode: bool = True

    # ── Helpers ──────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_type == "sqlite"

    def get_active_llm_providers(self) -> list[dict]:
        """Return list of configured LLM providers in priority order."""
        providers = []
        if self.deepseek_api_key:
            providers.append({
                "name": "deepseek",
                "model": f"deepseek/{self.deepseek_model}",
                "api_key": self.deepseek_api_key,
                "api_base": self.deepseek_base_url,
            })
        if self.glm_api_key:
            providers.append({
                "name": "glm",
                "model": f"openai/{self.glm_model}",
                "api_key": self.glm_api_key,
                "api_base": self.glm_base_url,
            })
        if self.openai_api_key:
            providers.append({
                "name": "openai",
                "model": self.openai_model,
                "api_key": self.openai_api_key,
            })
        return providers


@lru_cache()
def get_settings() -> Settings:
    return Settings()
