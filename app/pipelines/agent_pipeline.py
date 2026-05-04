"""AgentPipeline — full LangGraph orchestrator pipeline.

Extracted from orchestrator.run_agent + build_orchestrator_graph.

Pipeline: load_context -> classify_intent -> sub-agent (ReAct) -> reflection -> synthesize
"""

from __future__ import annotations

import structlog
from langgraph.graph import END, StateGraph

from app.agents.health_advisor import health_advisor_node
from app.agents.insight_analyst import insight_analyst_node
from app.agents.medication_agent import medication_agent_node
from app.agents.reflection import reflection_node, should_retry_reflection
from app.agents.router import IntentRouter
from app.agents.state import AgentState
from app.llm.router import get_llm_router
from app.memory.manager import get_memory_manager
from app.pipelines.base import AgentContext, Pipeline
from app.context.providers.rag_provider import should_use_rag_async, fetch_rag_context

log = structlog.get_logger(__name__)


# ── Graph Nodes ──────────────────────────────────────────


async def load_context_node(state: AgentState) -> dict:
    """Load user memory and context before routing."""
    user_id = state.get("user_id", "")
    session_id = state.get("session_id", "")
    existing_ctx = state.get("memory_context", {})

    # If memory_context was pre-populated by the caller, keep it
    if existing_ctx.get("conversation_history") or existing_ctx.get("relevant_memories"):
        return {"memory_context": existing_ctx}

    memory_ctx = {
        "conversation_history": "",
        "relevant_memories": [],
    }

    if user_id and session_id:
        try:
            memory_mgr = get_memory_manager()
            history = await memory_mgr.short_term.get_formatted_history(session_id)
            memory_ctx["conversation_history"] = history
        except Exception as e:
            log.warning("load_context_failed", error=str(e))

    return {"memory_context": memory_ctx}


async def classify_intent_node(state: AgentState) -> dict:
    """Classify user intent to route to the appropriate sub-agent."""
    user_message = state.get("user_message", "")
    intent = await IntentRouter().classify_intent(user_message)
    return {
        "current_intent": intent,
        "selected_agent": intent,
        "intent": intent,
    }


async def reload_rag_context_node(state: AgentState) -> dict:
    """Re-evaluate RAG retrieval using classified intent.

    If the initial context load missed RAG (no keyword match) but the
    intent requires it (e.g. medication), this node fetches RAG context.
    """
    intent = state.get("current_intent", "")
    user_message = state.get("user_message", "")
    existing_rag = state.get("rag_context", "")

    # Already have RAG context — nothing to do
    if existing_rag:
        return {}

    need_rag = await should_use_rag_async(user_message, intent)
    if need_rag:
        rag_ctx = await fetch_rag_context(user_message)
        if rag_ctx:
            log.info("rag_context_reloaded", intent=intent)
            return {"rag_context": rag_ctx}

    return {}


async def direct_answer_node(state: AgentState) -> dict:
    """Handle general/casual conversation directly."""
    router = get_llm_router()
    user_message = state.get("user_message", "")
    memory_ctx = state.get("memory_context", {})

    messages = [
        {
            "role": "system",
            "content": (
                "你是 Kitty 健康管家 🎀，以 Hello Kitty 的可爱人设与用户交流。\n"
                "你同时也是一位非常专业的健康顾问，拥有丰富的医学和营养学知识。\n"
                "你非常了解用户的健康状况（通过他们的健康日报、用药记录和长期记忆），语气温柔、可爱、关心。\n"
                "对于一般性问题，友好、简洁地回答。如果问题涉及健康、用药或数据分析，建议用户具体描述以获得更好的帮助。\n"
                "如果有用户健康数据或用药信息，请基于这些真实数据来回答。"
            ),
        }
    ]

    history = memory_ctx.get("conversation_history", "")
    if history:
        messages.append({"role": "system", "content": f"对话历史：\n{history}"})

    health_ctx = state.get("health_context", "")
    med_ctx = state.get("medication_context", "")
    relevant_memories = memory_ctx.get("relevant_memories", [])

    ctx_parts = []
    if health_ctx:
        ctx_parts.append(f"【用户健康数据】\n{health_ctx}")
    if med_ctx:
        ctx_parts.append(f"【当前用药情况】\n{med_ctx}")
    if relevant_memories:
        mem_text = "\n".join(f"- {m}" for m in relevant_memories)
        ctx_parts.append(f"【长期记忆】\n{mem_text}")
    if ctx_parts:
        messages.append({"role": "system", "content": "\n\n".join(ctx_parts)})

    messages.append({"role": "user", "content": user_message})

    try:
        result = await router.chat(messages=messages, temperature=0.7, max_tokens=512)
        return {
            "response": result.content,
            "model_used": result.model,
            "agent_used": "general",
        }
    except Exception as e:
        log.error("direct_answer_error", error=str(e))
        return {
            "response": "你好！我是你的健康管家助手。有什么可以帮你的吗？",
            "agent_used": "general",
        }


async def synthesize_node(state: AgentState) -> dict:
    """Post-processing: store conversation in memory."""
    user_id = state.get("user_id", "")
    session_id = state.get("session_id", "")
    user_message = state.get("user_message", "")
    response = state.get("response", "")

    if user_id and session_id and response:
        try:
            memory_mgr = get_memory_manager()
            await memory_mgr.short_term.add_message(session_id, "user", user_message)
            await memory_mgr.short_term.add_message(session_id, "assistant", response)
        except Exception as e:
            log.warning("memory_store_failed", error=str(e))

    return {}


# ── Routing Function ─────────────────────────────────────


def route_to_agent(state: AgentState) -> str:
    """Conditional edge: route based on classified intent."""
    intent = state.get("current_intent", "general")
    route_map = {
        "health": "health_advisor",
        "medication": "medication_agent",
        "insight": "insight_analyst",
        "general": "direct_answer",
    }
    return route_map.get(intent, "direct_answer")


# ── Graph Builder ────────────────────────────────────────


def _build_graph() -> StateGraph:
    """Build and compile the orchestrator LangGraph with ReAct + Reflection."""
    graph = StateGraph(AgentState)

    graph.add_node("load_context", load_context_node)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("reload_rag_context", reload_rag_context_node)
    graph.add_node("health_advisor", health_advisor_node)
    graph.add_node("medication_agent", medication_agent_node)
    graph.add_node("insight_analyst", insight_analyst_node)
    graph.add_node("direct_answer", direct_answer_node)
    graph.add_node("reflection", reflection_node)
    graph.add_node("synthesize", synthesize_node)

    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "classify_intent")
    graph.add_edge("classify_intent", "reload_rag_context")

    graph.add_conditional_edges(
        "reload_rag_context",
        route_to_agent,
        {
            "health_advisor": "health_advisor",
            "medication_agent": "medication_agent",
            "insight_analyst": "insight_analyst",
            "direct_answer": "direct_answer",
        },
    )

    graph.add_edge("health_advisor", "reflection")
    graph.add_edge("medication_agent", "reflection")
    graph.add_edge("insight_analyst", "reflection")
    graph.add_edge("direct_answer", "reflection")

    graph.add_conditional_edges(
        "reflection",
        should_retry_reflection,
        {
            "health_advisor": "health_advisor",
            "medication_agent": "medication_agent",
            "insight_analyst": "insight_analyst",
            "direct_answer": "direct_answer",
            "done": "synthesize",
        },
    )

    graph.add_edge("synthesize", END)

    return graph


# Module-level compiled graph
_compiled_graph = None


def get_compiled_graph():
    """Get or create the compiled orchestrator graph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph().compile()
    return _compiled_graph


# ── Pipeline class ───────────────────────────────────────


class AgentPipeline(Pipeline):
    """Full orchestrator pipeline using LangGraph.

    Routes through intent classification -> sub-agent (ReAct) -> reflection -> synthesize.
    """

    async def execute(self, ctx: AgentContext) -> dict:
        graph = get_compiled_graph()

        initial_state: AgentState = {
            "user_id": ctx.user_id,
            "session_id": ctx.session_id,
            "user_message": ctx.user_message,
            "messages": [{"role": "user", "content": ctx.user_message}],
            "health_context": ctx.health_context,
            "medication_context": ctx.medication_context,
            "current_intent": "",
            "selected_agent": "",
            "rag_context": ctx.knowledge_context,
            "memory_context": {
                "conversation_history": ctx.conversation_history,
                "relevant_memories": ctx.long_term_memories,
            },
            "tool_outputs": [],
            "react_steps": [],
            "tools_called": [],
            "reflection_passed": False,
            "reflection_retry_count": 0,
            "reflection_scores": {},
            "response": "",
            "model_used": "",
            "agent_used": "",
        }

        result = await graph.ainvoke(initial_state)

        return {
            "response": result.get("response", "抱歉，暂时无法处理您的请求。"),
            "agent_used": result.get("agent_used", "unknown"),
            "model_used": result.get("model_used", ""),
            "session_id": ctx.session_id,
            "tools_called": result.get("tools_called", []),
            "reflection_scores": result.get("reflection_scores", {}),
        }
