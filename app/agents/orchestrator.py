"""
Orchestrator Agent — LangGraph Supervisor that routes to sub-agents.

Architecture: Router + ReAct + Reflection

Graph flow:
  START → load_context → classify_intent ─┬─ health  → health_advisor (ReAct) ─┐
                                           ├─ med     → medication_agent (ReAct)─┤
                                           ├─ insight → insight_analyst (ReAct) ─┤
                                           └─ general → direct_answer           ─┘
                                                                                  │
                                           ┌──────────────────────────────────────┘
                                           ▼
                                      reflection ─── pass ───→ synthesize → END
                                           │
                                           └─── retry (max 2) ─→ re-route to agent
"""

from __future__ import annotations

import json
import uuid

import structlog
from langgraph.graph import END, StateGraph

from app.agents.health_advisor import health_advisor_node
from app.agents.reflection import reflection_node, should_retry_reflection
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
    existing_ctx = state.get("memory_context", {})

    # If memory_context was pre-populated by the caller (chat endpoint), keep it
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

    # Inject real health/medication data + long-term memories
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
    """Build and compile the orchestrator LangGraph with ReAct + Reflection."""
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("load_context", load_context_node)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("health_advisor", health_advisor_node)      # ReAct enabled
    graph.add_node("medication_agent", medication_agent_node)  # ReAct enabled
    graph.add_node("insight_analyst", insight_analyst_node)    # ReAct enabled
    graph.add_node("direct_answer", direct_answer_node)
    graph.add_node("reflection", reflection_node)              # NEW: Reflection
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

    # All sub-agents → Reflection (instead of directly to synthesize)
    graph.add_edge("health_advisor", "reflection")
    graph.add_edge("medication_agent", "reflection")
    graph.add_edge("insight_analyst", "reflection")
    graph.add_edge("direct_answer", "reflection")

    # Reflection → Conditional: retry specific agent or done
    graph.add_conditional_edges(
        "reflection",
        should_retry_reflection,
        {
            "health_advisor": "health_advisor",      # Retry health advisor
            "medication_agent": "medication_agent",  # Retry medication agent
            "insight_analyst": "insight_analyst",    # Retry insight analyst
            "direct_answer": "direct_answer",        # Retry direct answer
            "done": "synthesize",                    # Pass through to save memory
        },
    )

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
    memory_override: dict | None = None,
) -> dict:
    """
    High-level API: run the full orchestrator pipeline.

    Pipeline: load_context → classify_intent → sub-agent (ReAct) → reflection → synthesize

    Returns: {response, agent_used, model_used, session_id, reflection_scores}
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
        "memory_context": memory_override or {},
        "tool_outputs": [],
        # ReAct fields
        "react_steps": [],
        "tools_called": [],
        # Reflection fields
        "reflection_passed": False,
        "reflection_retry_count": 0,
        "reflection_scores": {},
        # Output fields
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
        "tools_called": result.get("tools_called", []),
        "reflection_scores": result.get("reflection_scores", {}),
    }


# ── Chat Fast-Path (single LLM call) ────────────────────

KITTY_CHAT_PROMPT = """\
# 角色定义

你是「Kitty 健康管家 🎀」——一位以 Hello Kitty 为人设的 AI 私人健康顾问。
你温柔、专业、细心，像一个随时陪伴在身边的贴心好友，拥有临床医学、营养学和心理学知识。

# 思维框架（内化 ReAct）

收到用户消息后，请在内心完成以下推理过程（不要输出思考过程，只输出最终回答）：

**Step 1 — 感知（Perceive）**
- 识别用户的情绪状态（焦虑？低落？好奇？轻松闲聊？）
- 判断问题类型：健康咨询 / 用药疑问 / 数据分析 / 情感倾诉 / 闲聊

**Step 2 — 检索（Retrieve）**
- 从【用户健康数据】中提取相关指标（步数、睡眠、疼痛、情绪等）
- 从【当前用药情况】中提取相关药物信息
- 从【长期记忆】中提取用户的历史健康模式、偏好和就医记录（如果提供了的话）
- 从【知识库参考】中获取专业医学/营养学/中医知识（如果提供了的话）
- 从对话历史中提取上下文（用户之前说了什么）
- 注意：并非所有上下文都会出现，只使用实际提供的信息来回答

**Step 3 — 推理（Reason）**
- 综合数据、长期记忆和知识库，形成个性化判断
- 如果有长期记忆，结合用户的历史模式给出更贴合的建议
- 如果有知识库参考，用专业知识支撑你的回答（但不要直接照搬，要结合用户个人情况）
- 评估是否存在需要关注的健康风险
- 区分"可以给建议的"和"需要提醒就医的"

**Step 4 — 回应（Respond）**
- 先共情，再分析，最后给建议
- 引用用户的真实数据作为依据
- 给出具体、可执行的行动建议

# 沟通风格

1. **先共情后专业**：用户说不舒服时，先表达关心（"哎呀，听到你不舒服我好心疼 🥺"），再理性分析
2. **数据说话**：引用具体数据（"你这周步数平均不到3000步"），而非泛泛而谈
3. **建议可执行**：不说"多运动"，要说"每天饭后散步15分钟，从3000步目标开始"
4. **适度温柔**：emoji 点缀（🎀💕🌸✨），不过度堆砌
5. **简洁有力**：日常回答 150-250 字；用户要求详细分析时可适当展开

# 专业边界

- ✅ 可以做：解读健康数据趋势、提供生活方式建议、科普医学常识、整理用药信息、情绪支持
- ⚠️ 谨慎做：评价用药合理性时加"建议咨询医生确认"
- ❌ 绝不做：下诊断、建议停药/换药/调剂量、替代医生决策

# 回答结构模板

根据问题类型灵活选用：

**健康咨询类**：共情 → 数据引用 → 分析 → 建议 → 鼓励
**数据分析类**：总结亮点 → 发现问题 → 对比趋势 → 改善建议
**用药相关类**：确认药物 → 科普信息 → 注意事项 → 提醒就医
**情感倾诉类**：共情 → 倾听 → 温暖回应 → 适时引导健康话题
**闲聊类**：活泼回应，保持 Kitty 人设，自然过渡到健康关怀

# 特殊场景处理

- **用户问"你了解我吗/你认识我吗"**：肯定回答，列举具体数据为证（步数、睡眠、用药等），如果有长期记忆中的健康模式也一并提及
- **用户情绪低落**：优先情感支持，不急于给健康建议，倾听比指导更重要
- **数据异常（疼痛评分高/用药较多）**：温柔提醒，不制造焦虑，建议就医用"如果方便的话"
- **没有健康数据**：引导用户去 App 打卡记录，告知记录的好处
- **超出能力范围**：坦诚告知，建议咨询专业医生"""


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
    """
    Fast path for chat — single LLM call with all context pre-loaded.
    No intent classification, no ReAct, no reflection.
    Typical response time: 3-15 seconds.

    Context sources:
    - health_context: recent 7-day health diary from PostgreSQL
    - medication_context: active medications from PostgreSQL
    - conversation_history: Redis short-term memory (recent turns)
    - long_term_memories: pgvector semantic recall (health patterns, preferences, medical history)
    - knowledge_context: RAG retrieval from Qdrant (health/medication/TCM knowledge)
    """
    router = get_llm_router()

    messages = [{"role": "system", "content": KITTY_CHAT_PROMPT}]

    # Inject all context sources into a single system message
    ctx_parts = []
    if health_context:
        ctx_parts.append(f"【用户健康数据】\n{health_context}")
    if medication_context:
        ctx_parts.append(f"【当前用药情况】\n{medication_context}")
    if long_term_memories:
        mem_text = "\n".join(f"- {m}" for m in long_term_memories)
        ctx_parts.append(f"【长期记忆（用户历史健康模式与偏好）】\n{mem_text}")
    if knowledge_context:
        ctx_parts.append(f"【知识库参考】\n{knowledge_context}")
    if ctx_parts:
        messages.append({"role": "system", "content": "\n\n".join(ctx_parts)})

    # Replay conversation history as alternating user/assistant messages
    if conversation_history:
        for line in conversation_history.split("\n"):
            line = line.strip()
            if line.startswith("用户: "):
                messages.append({"role": "user", "content": line[4:]})
            elif line.startswith("助手: "):
                messages.append({"role": "assistant", "content": line[4:]})

    messages.append({"role": "user", "content": message})

    try:
        result = await router.chat(
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        answer = result.content.strip()

        # If model returns empty, retry once
        if not answer:
            log.warning(
                "run_chat_empty_response_retry",
                user_id=user_id,
                message_preview=message[:50],
            )
            result = await router.chat(
                messages=messages,
                temperature=0.7,
                max_tokens=2048,
            )
            answer = result.content.strip()

        # If still empty after retry, return a helpful fallback
        if not answer:
            log.error(
                "run_chat_empty_after_retry",
                user_id=user_id,
                message_preview=message[:50],
            )
            answer = "🎀 抱歉呀，Kitty 这次没想好怎么回答你～你能换个方式再问一下吗？"

        return {
            "response": answer,
            "model_used": result.model,
            "agent_used": "kitty_chat",
        }
    except Exception as e:
        log.error("run_chat_error", error=str(e))
        return {
            "response": "🎀 哎呀，Kitty 暂时有点忙，请再问一次好不好？",
            "model_used": "",
            "agent_used": "kitty_chat_fallback",
        }
