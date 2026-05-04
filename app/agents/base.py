"""Agent base class — unified tool registration, memory injection, and ReAct loop abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog
from langchain_core.tools import BaseTool

from app.agents.state import AgentState
from app.llm.router import get_llm_router

log = structlog.get_logger(__name__)


class BaseAgent(ABC):
    """Abstract base for sub-agents (health_advisor, medication_agent, insight_analyst).

    Provides:
    - Tool registration via ``tools`` property
    - Memory/context injection helpers
    - ReAct loop abstraction via ``react()``
    """

    name: str = "base"

    def __init__(self) -> None:
        self._tools: list[BaseTool] = []
        self._register_tools()

    # ── Tool registration ──────────────────────────────────

    @abstractmethod
    def _register_tools(self) -> None:
        """Populate ``self._tools`` with the agent's available tools."""

    @property
    def tools(self) -> list[BaseTool]:
        return self._tools

    def tool_map(self) -> dict[str, BaseTool]:
        return {t.name: t for t in self._tools}

    # ── Context helpers ────────────────────────────────────

    @staticmethod
    def build_memory_block(state: AgentState) -> str:
        """Format memory context from state into a prompt block."""
        memory_ctx = state.get("memory_context", {})
        parts: list[str] = []

        health_ctx = state.get("health_context", "")
        if health_ctx:
            parts.append(f"【用户健康数据】\n{health_ctx}")

        med_ctx = state.get("medication_context", "")
        if med_ctx:
            parts.append(f"【当前用药情况】\n{med_ctx}")

        memories = memory_ctx.get("relevant_memories", [])
        if memories:
            mem_text = "\n".join(f"- {m}" for m in memories)
            parts.append(f"【长期记忆】\n{mem_text}")

        rag_ctx = state.get("rag_context", "")
        if rag_ctx:
            parts.append(f"【知识库参考】\n{rag_ctx}")

        return "\n\n".join(parts)

    # ── ReAct loop ─────────────────────────────────────────

    @abstractmethod
    async def react(self, state: AgentState) -> dict:
        """Execute the agent's ReAct loop and return state updates."""
