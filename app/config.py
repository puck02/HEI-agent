"""
Application configuration — loads from .env via pydantic-settings.
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

    # ── PostgreSQL ───────────────────────────────────────
    database_url: str = "postgresql+asyncpg://helagent:helagent_password@localhost:5432/helagent?ssl=disable"
    database_url_sync: str = "postgresql://helagent:helagent_password@localhost:5432/helagent?sslmode=disable"

    # ── Redis ────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Qdrant ───────────────────────────────────────────
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None

    # ── JWT ──────────────────────────────────────────────
    jwt_secret_key: str = "change-this-to-a-random-secret-key-in-production"
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
    llm_request_timeout_seconds: float = 22.0
    chat_pipeline_timeout_seconds: float = 28.0
    chat_inference_timeout_seconds: float = 16.0
    chat_history_max_messages: int = 6
    chat_history_max_chars: int = 1200

    # ── Embedding ────────────────────────────────────────
    embedding_provider: str = "glm"
    embedding_model: str = "embedding-3"

    # ── RAG ──────────────────────────────────────────────
    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 200
    rag_top_k: int = 5
    rag_rerank_top_k: int = 20

    # ── Memory ───────────────────────────────────────────
    short_term_memory_ttl: int = 86400  # 24h seconds
    short_term_memory_max_turns: int = 20
    long_term_memory_decay_rate: float = 0.95

    # ── MCP Tools ────────────────────────────────────────
    weather_api_key: Optional[str] = None
    search_api_key: Optional[str] = None

    # ── Push (FCM) ───────────────────────────────────────
    fcm_service_account_json: Optional[str] = None

    # ── Helpers ──────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

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
