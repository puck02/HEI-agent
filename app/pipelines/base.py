"""Pipeline base class and AgentContext shared data class."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import structlog

from app.context.assembler import ContextAssembler

log = structlog.get_logger(__name__)


@dataclass
class AgentContext:
    """Shared context that flows through a pipeline execution.

    Populated by ``load()`` before the pipeline runs, and extended by
    intermediate agent results via ``intermediate_results``.
    """

    user_id: str
    session_id: str
    user_message: str

    # ── Data loaded by ContextAssembler ────────────────────
    health_context: str = ""
    medication_context: str = ""
    conversation_history: str = ""
    long_term_memories: list[str] = field(default_factory=list)
    knowledge_context: str = ""
    knowledge_refs: list[dict] = field(default_factory=list)

    # ── Runtime shared state between agents ────────────────
    intermediate_results: dict = field(default_factory=dict)

    # ── Classified intent (set after initial load) ──────────
    intent: str = ""

    async def load(self, assembler: ContextAssembler, intent: str = "") -> None:
        """Load all data sources in parallel via the assembler.

        Args:
            assembler: The context assembler instance.
            intent: Classified intent — passed to RAGDecider for smarter
                    retrieval decisions. If empty, falls back to keyword matching.
        """
        data = await assembler.load_all(
            user_id=uuid.UUID(self.user_id) if self.user_id else uuid.UUID(int=0),
            session_id=self.session_id,
            message=self.user_message,
            intent=intent or self.intent,
        )
        self.health_context = data.get("health_context", "")
        self.medication_context = data.get("medication_context", "")
        self.conversation_history = data.get("conversation_history", "")
        self.long_term_memories = data.get("long_term_memories", [])
        self.knowledge_context = data.get("knowledge_context", "")
        self.knowledge_refs = data.get("knowledge_refs", [])


class Pipeline(ABC):
    """Abstract base class for execution pipelines.

    Subclasses implement ``execute()`` which receives a fully-loaded
    ``AgentContext`` and returns a result dict.
    """

    def __init__(self, assembler: ContextAssembler | None = None) -> None:
        self.assembler = assembler or ContextAssembler()

    @abstractmethod
    async def execute(self, ctx: AgentContext) -> dict:
        """Run the pipeline and return a result dict with at least 'response'."""
