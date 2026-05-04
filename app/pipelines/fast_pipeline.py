"""FastPipeline — single LLM call with all context pre-loaded.

Extracted from orchestrator.run_chat.  No intent classification, no ReAct,
no reflection — typical response time 3-15 s.
"""

from __future__ import annotations

import structlog

from app.config import get_settings
from app.llm.router import get_llm_router
from app.pipelines.base import AgentContext, Pipeline

log = structlog.get_logger(__name__)

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


class FastPipeline(Pipeline):
    """Single LLM call pipeline — fastest path for chat.

    All context is pre-loaded into the prompt; no classification,
    no ReAct, no reflection.
    """

    async def execute(self, ctx: AgentContext) -> dict:
        router = get_llm_router()
        settings = get_settings()

        messages: list[dict] = [{"role": "system", "content": KITTY_CHAT_PROMPT}]

        # Inject all context sources into a single system message
        ctx_parts: list[str] = []
        if ctx.health_context:
            ctx_parts.append(f"【用户健康数据】\n{ctx.health_context}")
        if ctx.medication_context:
            ctx_parts.append(f"【当前用药情况】\n{ctx.medication_context}")
        if ctx.long_term_memories:
            mem_text = "\n".join(f"- {m}" for m in ctx.long_term_memories)
            ctx_parts.append(f"【长期记忆（用户历史健康模式与偏好）】\n{mem_text}")
        if ctx.knowledge_context:
            ctx_parts.append(f"【知识库参考】\n{ctx.knowledge_context}")
        if ctx_parts:
            messages.append({"role": "system", "content": "\n\n".join(ctx_parts)})

        # Replay conversation history as alternating user/assistant messages
        if ctx.conversation_history:
            for line in ctx.conversation_history.split("\n"):
                line = line.strip()
                if line.startswith("用户: "):
                    messages.append({"role": "user", "content": line[4:]})
                elif line.startswith("助手: "):
                    messages.append({"role": "assistant", "content": line[4:]})

        messages.append({"role": "user", "content": ctx.user_message})

        try:
            dynamic_max_tokens = 640 if len(ctx.user_message) > 120 else 448

            result = await router.chat(
                messages=messages,
                temperature=0.7,
                max_tokens=dynamic_max_tokens,
                timeout=settings.chat_inference_timeout_seconds,
            )
            answer = result.content.strip()

            # Empty-response retry
            if not answer:
                log.warning(
                    "run_chat_empty_response_retry",
                    user_id=ctx.user_id,
                    message_preview=ctx.user_message[:50],
                )
                result = await router.chat(
                    messages=[
                        *messages,
                        {
                            "role": "system",
                            "content": "请直接输出最终回答，不要留空，不要输出思考过程。",
                        },
                    ],
                    temperature=0.4,
                    max_tokens=448,
                    timeout=settings.chat_inference_timeout_seconds,
                )
                answer = result.content.strip()

            if not answer:
                log.error(
                    "run_chat_empty_after_retry",
                    user_id=ctx.user_id,
                    message_preview=ctx.user_message[:50],
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
