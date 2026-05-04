"""
Orchestrator Agent — compatibility wrapper.

The actual logic has been refactored into:
  - app.pipelines.fast_pipeline   (FastPipeline — single LLM call)
  - app.pipelines.agent_pipeline  (AgentPipeline — full LangGraph graph)
  - app.agents.router             (IntentRouter)
  - app.agents.base               (BaseAgent)
  - app.context.assembler         (ContextAssembler)
  - app.context.providers.*       (health, medication, memory, RAG providers)

This module re-exports the original public API so existing imports keep working.
"""

from __future__ import annotations

from app.agents.health_advisor import health_advisor_node  # noqa: F401
from app.agents.insight_analyst import insight_analyst_node  # noqa: F401
from app.agents.medication_agent import medication_agent_node  # noqa: F401
from app.agents.reflection import reflection_node, should_retry_reflection  # noqa: F401
from app.agents.router import IntentRouter  # noqa: F401
from app.pipelines.agent_pipeline import (
    AgentPipeline,
    classify_intent_node,  # noqa: F401
    direct_answer_node,  # noqa: F401
    get_compiled_graph,
    load_context_node,  # noqa: F401
    route_to_agent,  # noqa: F401
    synthesize_node,  # noqa: F401
)
from app.pipelines.fast_pipeline import FastPipeline, KITTY_CHAT_PROMPT  # noqa: F401

# Re-export graph builder under original name for backwards compat
build_orchestrator_graph = get_compiled_graph


def get_orchestrator():
    """Get or create the compiled orchestrator graph (legacy alias)."""
    return get_compiled_graph()


async def run_agent(
    user_id: str,
    session_id: str,
    message: str,
    health_context: str = "",
    medication_context: str = "",
    memory_override: dict | None = None,
) -> dict:
    """High-level API: run the full orchestrator pipeline (compatibility wrapper)."""
    from app.context.assembler import ContextAssembler
    from app.pipelines.base import AgentContext

    ctx = AgentContext(
        user_id=user_id,
        session_id=session_id,
        user_message=message,
        health_context=health_context,
        medication_context=medication_context,
    )
    if memory_override:
        ctx.conversation_history = memory_override.get("conversation_history", "")
        ctx.long_term_memories = memory_override.get("relevant_memories", [])

    pipeline = AgentPipeline(assembler=ContextAssembler(db=None))
    return await pipeline.execute(ctx)


async def run_chat(
    user_id: str,
    session_id: str,
    message: str,
    health_context: str = "",
    medication_context: str = "",
    conversation_history: str = "",
    long_term_memories: list[str] | None = None,
    knowledge_context: str = "",
) -> dict:
    """Fast path for chat — single LLM call (compatibility wrapper)."""
    from app.context.assembler import ContextAssembler
    from app.pipelines.base import AgentContext

    ctx = AgentContext(
        user_id=user_id,
        session_id=session_id,
        user_message=message,
        health_context=health_context,
        medication_context=medication_context,
        conversation_history=conversation_history,
        long_term_memories=long_term_memories or [],
        knowledge_context=knowledge_context,
    )

    pipeline = FastPipeline(assembler=ContextAssembler(db=None))
    return await pipeline.execute(ctx)
