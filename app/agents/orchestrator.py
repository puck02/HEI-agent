"""
Orchestrator Agent — LangGraph Supervisor that routes to sub-agents.

Graph flow:
  START → load_context → classify_intent ─┬─ health  → health_advisor  → synthesize → END
                                           ├─ med     → medication_agent → synthesize → END
                                           ├─ insight → insight_analyst  → synthesize → END
                                           └─ general → direct_answer    → synthesize → END
"""

from __future__ import annotations

import json
import uuid

import structlog
from langgraph.graph import END, StateGraph

from app.agents.health_advisor import health_advisor_node
from app.utils.json_parser import parse_llm_json
from app.agents.insight_analyst import insight_analyst_node
from app.agents.medication_agent import medication_agent_node
from app.agents.state import AgentState
from app.llm.router import get_llm_router
from app.memory.manager import get_memory_manager

log = structlog.get_logger(__name__)


# ── Graph Nodes ──────────────────────────────────────────


async def load_context_node(state: AgentState) -> dict:
    """Load user memory and context before routing."""
    user_id = state.get("user_id", "")
    session_id = state.get("session_id", "")
    user_message = state.get("user_message", "")

    memory_ctx = {
        "conversation_history": "",
        "relevant_memories": [],
    }

    if user_id and session_id:
        try:
            # We'll use memory manager without DB session here
            # The short-term memory (Redis) doesn't need a DB session
            memory_mgr = get_memory_manager()
            history = await memory_mgr.short_term.get_formatted_history(session_id)
            memory_ctx["conversation_history"] = history
        except Exception as e:
            log.warning("load_context_failed", error=str(e))

    return {
        "memory_context": memory_ctx,
    }


async def classify_intent_node(state: AgentState) -> dict:
    """Classify user intent to route to the appropriate sub-agent."""
    router = get_llm_router()
    user_message = state.get("user_message", "")

    prompt = f"""请分析以下用户消息的意图，返回一个 JSON：

用户消息: "{user_message}"

意图分类：
- health: 健康相关咨询（症状、睡眠、运动、饮食、情绪、日报建议等）
- medication: 用药相关（药品查询、用药记录、药品说明、剂量等）
- insight: 数据分析相关（趋势、洞察、统计、报告、对比等）
- general: 其他一般对话（问候、闲聊、设置等）

只返回 JSON：{{"intent": "health|medication|insight|general"}}"""

    try:
        result = await router.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=50,
            response_format={"type": "json_object"},
        )
        data = parse_llm_json(result.content)
        intent = data.get("intent", "general")
        if intent not in ("health", "medication", "insight", "general"):
            intent = "general"
    except Exception as e:
        log.warning("intent_classification_failed", error=str(e), fallback="general")
        intent = "general"

    log.info("intent_classified", intent=intent, message=user_message[:50])
    return {
        "current_intent": intent,
        "selected_agent": intent,
    }


async def direct_answer_node(state: AgentState) -> dict:
    """Handle general/casual conversation directly."""
    router = get_llm_router()
    user_message = state.get("user_message", "")
    memory_ctx = state.get("memory_context", {})

    messages = [
        {
            "role": "system",
            "content": "你是 HElDairy 健康管家助手。对于一般性问题，友好、简洁地回答。如果问题涉及健康、用药或数据分析，建议用户具体描述以获得更好的帮助。",
        }
    ]

    history = memory_ctx.get("conversation_history", "")
    if history:
        messages.append({"role": "system", "content": f"对话历史：\n{history}"})

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
    """
    Post-processing: store conversation in memory.
    The response is already set by the sub-agent.
    """
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


# ── Build Graph ──────────────────────────────────────────


def build_orchestrator_graph() -> StateGraph:
    """Build and compile the orchestrator LangGraph."""
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("load_context", load_context_node)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("health_advisor", health_advisor_node)
    graph.add_node("medication_agent", medication_agent_node)
    graph.add_node("insight_analyst", insight_analyst_node)
    graph.add_node("direct_answer", direct_answer_node)
    graph.add_node("synthesize", synthesize_node)

    # Set entry point
    graph.set_entry_point("load_context")

    # Edges
    graph.add_edge("load_context", "classify_intent")

    # Conditional routing from classify_intent
    graph.add_conditional_edges(
        "classify_intent",
        route_to_agent,
        {
            "health_advisor": "health_advisor",
            "medication_agent": "medication_agent",
            "insight_analyst": "insight_analyst",
            "direct_answer": "direct_answer",
        },
    )

    # All sub-agents → synthesize → END
    graph.add_edge("health_advisor", "synthesize")
    graph.add_edge("medication_agent", "synthesize")
    graph.add_edge("insight_analyst", "synthesize")
    graph.add_edge("direct_answer", "synthesize")
    graph.add_edge("synthesize", END)

    return graph


# Module-level compiled graph
_compiled_graph = None


def get_orchestrator():
    """Get or create the compiled orchestrator graph."""
    global _compiled_graph
    if _compiled_graph is None:
        graph = build_orchestrator_graph()
        _compiled_graph = graph.compile()
    return _compiled_graph


async def run_agent(
    user_id: str,
    session_id: str,
    message: str,
    health_context: str = "",
    medication_context: str = "",
) -> dict:
    """
    High-level API: run the full orchestrator pipeline.

    Returns: {response, agent_used, model_used, session_id}
    """
    orchestrator = get_orchestrator()

    initial_state: AgentState = {
        "user_id": user_id,
        "session_id": session_id,
        "user_message": message,
        "messages": [{"role": "user", "content": message}],
        "health_context": health_context,
        "medication_context": medication_context,
        "current_intent": "",
        "selected_agent": "",
        "rag_context": "",
        "memory_context": {},
        "tool_outputs": [],
        "response": "",
        "model_used": "",
        "agent_used": "",
    }

    result = await orchestrator.ainvoke(initial_state)

    return {
        "response": result.get("response", "抱歉，暂时无法处理您的请求。"),
        "agent_used": result.get("agent_used", "unknown"),
        "model_used": result.get("model_used", ""),
        "session_id": session_id,
    }
