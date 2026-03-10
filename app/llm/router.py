"""
LLM Router — unified interface with automatic failover across providers.

Uses LiteLLM under the hood to normalize DeepSeek / GLM / OpenAI calls.
Priority: deepseek → glm → openai (configurable).
If one provider's key is invalid or times out, automatically tries the next.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog
from litellm import acompletion, aembedding
from litellm.exceptions import (
    AuthenticationError,
    BadRequestError,
    RateLimitError,
    ServiceUnavailableError,
)

from app.config import get_settings

log = structlog.get_logger(__name__)

# Errors that should trigger failover to the next provider
FAILOVER_EXCEPTIONS = (
    AuthenticationError,
    RateLimitError,
    ServiceUnavailableError,
    TimeoutError,
    ConnectionError,
)


@dataclass
class ProviderConfig:
    name: str
    model: str
    api_key: str
    api_base: str | None = None
    enabled: bool = True
    consecutive_failures: int = 0
    last_failure_time: float = 0
    # Disable provider for 5 minutes after 3 consecutive failures
    max_consecutive_failures: int = 3
    cooldown_seconds: float = 300

    @property
    def is_available(self) -> bool:
        if not self.enabled or not self.api_key:
            return False
        if self.consecutive_failures >= self.max_consecutive_failures:
            elapsed = time.time() - self.last_failure_time
            if elapsed < self.cooldown_seconds:
                return False
            # Cooldown expired — reset and allow retry
            self.consecutive_failures = 0
        return True

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        self.last_failure_time = time.time()


@dataclass
class LLMCallResult:
    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0


class LLMRouter:
    """Multi-provider LLM router with automatic failover."""

    def __init__(self) -> None:
        settings = get_settings()
        self.providers: list[ProviderConfig] = []
        for p in settings.get_active_llm_providers():
            self.providers.append(
                ProviderConfig(
                    name=p["name"],
                    model=p["model"],
                    api_key=p["api_key"],
                    api_base=p.get("api_base"),
                )
            )
        log.info(
            "llm_router_init",
            providers=[p.name for p in self.providers],
            active=[p.name for p in self.providers if p.is_available],
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: dict | None = None,
        preferred_provider: str | None = None,
        **kwargs: Any,
    ) -> LLMCallResult:
        """
        Send chat completion request. Tries providers in priority order.
        If preferred_provider is set and available, use it first.
        """
        providers = self._ordered_providers(preferred_provider)
        last_error: Exception | None = None

        for provider in providers:
            if not provider.is_available:
                continue

            call_kwargs: dict[str, Any] = {
                "model": provider.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "api_key": provider.api_key,
                **kwargs,
            }
            if provider.api_base:
                call_kwargs["api_base"] = provider.api_base
            if response_format:
                call_kwargs["response_format"] = response_format

            start = time.time()
            try:
                resp = await acompletion(**call_kwargs)
                latency = (time.time() - start) * 1000

                provider.record_success()

                msg = resp.choices[0].message
                content = msg.content or ""
                usage = {}
                if resp.usage:
                    usage = {
                        "prompt_tokens": resp.usage.prompt_tokens,
                        "completion_tokens": resp.usage.completion_tokens,
                        "total_tokens": resp.usage.total_tokens,
                    }

                # Reasoning models (GLM-4.7 etc.) may put all tokens into
                # reasoning_content and return empty content when max_tokens
                # is too low.  Extract reasoning_content for diagnostics.
                reasoning = ""
                try:
                    dump = msg.model_dump()
                    reasoning = (
                        dump.get("reasoning_content")
                        or (dump.get("provider_specific_fields") or {}).get("reasoning_content")
                        or ""
                    )
                except Exception:
                    pass

                if not content and reasoning:
                    log.warning(
                        "llm_empty_content_with_reasoning",
                        provider=provider.name,
                        model=provider.model,
                        reasoning_len=len(reasoning),
                        tokens=usage.get("total_tokens", 0),
                    )

                log.info(
                    "llm_call_success",
                    provider=provider.name,
                    model=provider.model,
                    latency_ms=round(latency, 1),
                    tokens=usage.get("total_tokens", 0),
                    has_reasoning=bool(reasoning),
                )
                return LLMCallResult(
                    content=content,
                    model=provider.model,
                    provider=provider.name,
                    usage=usage,
                    latency_ms=latency,
                )

            except FAILOVER_EXCEPTIONS as e:
                latency = (time.time() - start) * 1000
                provider.record_failure()
                last_error = e
                log.warning(
                    "llm_call_failover",
                    provider=provider.name,
                    error=str(e),
                    latency_ms=round(latency, 1),
                    consecutive_failures=provider.consecutive_failures,
                )
                continue

            except Exception as e:
                latency = (time.time() - start) * 1000
                provider.record_failure()
                last_error = e
                log.error(
                    "llm_call_error",
                    provider=provider.name,
                    error=str(e),
                    latency_ms=round(latency, 1),
                )
                continue

        raise RuntimeError(
            f"All LLM providers failed. Last error: {last_error}"
        )

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """Generate embeddings using the configured embedding provider."""
        settings = get_settings()
        _model = model or f"openai/{settings.embedding_model}"

        # Determine API key and base for embedding provider
        provider_map = {
            "glm": (settings.glm_api_key, settings.glm_base_url),
            "openai": (settings.openai_api_key, None),
            "deepseek": (settings.deepseek_api_key, settings.deepseek_base_url),
        }
        api_key, api_base = provider_map.get(
            settings.embedding_provider, (settings.glm_api_key, settings.glm_base_url)
        )

        call_kwargs: dict[str, Any] = {
            "model": _model,
            "input": texts,
            "api_key": api_key,
        }
        if api_base:
            call_kwargs["api_base"] = api_base

        resp = await aembedding(**call_kwargs)
        return [item["embedding"] for item in resp.data]

    def _ordered_providers(self, preferred: str | None) -> list[ProviderConfig]:
        """Return providers list with preferred one moved to front."""
        if not preferred:
            return list(self.providers)
        preferred_list = [p for p in self.providers if p.name == preferred]
        others = [p for p in self.providers if p.name != preferred]
        return preferred_list + others

    def get_status(self) -> list[dict]:
        """Return status of all providers (for health check / admin)."""
        return [
            {
                "name": p.name,
                "model": p.model,
                "enabled": p.enabled,
                "available": p.is_available,
                "consecutive_failures": p.consecutive_failures,
            }
            for p in self.providers
        ]


# Module-level singleton
_router: LLMRouter | None = None


def get_llm_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
