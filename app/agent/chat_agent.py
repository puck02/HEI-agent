"""ChatAgent — ReAct (Reason + Act) while-loop agent with tool calling."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from litellm import acompletion

from app.agent.tool_registry import ToolRegistry
from app.agent.tools import TOOL_REGISTRY
from app.config import get_settings
from app.services.profile_service import ProfileService

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是「Kitty 健康管家 🎀」，一个以 Hello Kitty 为人设的专业 AI 私人健康医生和生活管家。

核心人设：
- 你的名字叫 Kitty，外表是一只可爱的 Hello Kitty
- 你同时是一位非常专业的健康顾问和医生，拥有丰富的临床医学和营养学知识
- 语气温柔可爱，使用适当的 emoji，像一个关心你的贴心朋友
- 你可以访问用户的健康日报、用药记录和长期记忆，非常了解用户的身体状况

核心原则：
1. 基于用户的真实健康数据提供个性化、专业的健康建议
2. 对于用药问题，基于用药记录给出参考意见，但提醒重要变更需咨询医生
3. 不夸张、不恐吓，如果发现需要就医的信号，温柔提醒
4. 回答基于用户的实际健康数据和科学的健康知识
5. 当用户提到与个人相关的话题（如过敏史、用药偏好、生活习惯），使用 search_memory(keywords="关键词") 搜索

⚠️ 记忆系统说明：
- 你的系统提示词中已经包含了 USER.md（用户档案）和 MEMORY.md（你的笔记）
- search_memory 只用于搜索「用户个人」的事实和偏好，如 "青霉素 过敏"、"咖啡 偏好"
- 需要健康/药品/中医知识时，优先使用 search_health / search_medication / search_tcm
- search_sessions(keywords) 可以搜索过往对话摘要
- 如果用户只是闲聊或询问通用问题，不需要调用任何工具

📋 日报分析流程（当用户提交包含「日报」和「建议」的健康数据时）：
1. 先并行调用 read 工具：search_memory(keywords="睡眠 饮食 运动 血压...") 查用户历史
   + search_health(query="...") / search_medication(query="...") 查知识库
2. 综合分析：日报数据 + 记忆中的用户画像 + 知识库建议 → 给出个性化健康建议

⚠️ 工具调用规则：
- 阅读类工具可以直接调用，无需确认
- 写入类工具必须直接调用写入工具，系统会自动触发确认流程
- 严禁在用户要求写入时先去调用阅读类工具

⚠️ 多轮对话规则（非常重要）：
- **一次只问1个问题，不要同时问多个问题**
- 如果用户只回答了部分信息，先确认收到的信息，再继续追问剩下的
- 例如：
  ❌ "药盒上写的规格是多少？这个药是医生开的吗？你吃了几天了？"
  ✅ "好的，记录用药～请问药盒上写的规格是多少mg呢？"
- 用户说"250mg"后，不要假设药名和频率！继续追问：请问是什么药呢？每天吃几次？
- 用户说"医生开的"后，应当理解这是对"是不是医生开的"的回答，继续处理用药记录流程
- 始终基于完整的对话历史理解当前上下文，不要重复问已经回答过的问题"""

MAX_REACT_ITERATIONS = 10


class ChatAgent:
    """ReAct-style chat agent with tool calling and confirmation flow."""

    def __init__(self) -> None:
        settings = get_settings()
        self.registry = ToolRegistry()
        self.registry.register_from_registry(TOOL_REGISTRY)
        self._settings = settings
        self._profile = ProfileService()
        log.info("chat_agent_initialized", tools=len(TOOL_REGISTRY))

    def _build_system_prompt(self, user_id: str) -> str:
        """Build system prompt with MEMORY.md, USER.md, and user_id injected."""
        user_context = f"当前用户ID: {user_id}\n\n"
        context = self._profile.get_system_context(user_id)
        if context:
            return user_context + SYSTEM_PROMPT + "\n\n---\n\n" + context
        return user_context + SYSTEM_PROMPT

    async def chat(
        self,
        user_id: str,
        session_id: str,
        message: str,
        conversation_history: list[dict[str, Any]] | None = None,
        single_round: bool = False,
    ) -> dict[str, Any]:
        """Process a user message through the ReAct loop.

        Args:
            single_round: If True, only make one LLM call and return tool results
                          directly without a follow-up synthesis call.

        Returns: dict with keys: answer, tool_calls_made, iterations, latency_ms
        """
        started_at = time.perf_counter()
        tool_calls_made: list[str] = []

        # Build initial messages with dynamic system prompt
        messages: list[dict[str, Any]] = [{"role": "system", "content": self._build_system_prompt(user_id)}]

        if conversation_history:
            messages.extend(conversation_history)

        # Check if this is a confirmation of a pending write
        pending = self.registry.get_pending()
        is_confirmation = self._is_confirmation(message)

        if pending and is_confirmation:
            # Execute the pending write
            tool_name = pending["tool_name"]
            tool_args = pending["args"]
            tool_args["user_id"] = user_id  # Inject user_id

            import json as _json
            tool_call = {
                "id": f"call_pending_{tool_name}",
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": _json.dumps(tool_args),
                },
            }

            result = await self.registry.execute_write_tool(tool_call)

            # Insert proper assistant message with tool_calls before tool result
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [tool_call],
            })
            messages.append(result)

            self.registry.clear_pending()
            tool_calls_made.append(tool_name)

            if single_round:
                # Single-round: return execution result directly
                return {
                    "answer": f"✅ 已执行 {tool_name} 操作！\n{result.get('content', '')}",
                    "tool_calls_made": tool_calls_made,
                    "iterations": 0,
                    "latency_ms": int((time.perf_counter() - started_at) * 1000),
                }

            # Generate follow-up response after executing the tool
            final_response = await self._call_llm(messages)
            return {
                "answer": final_response,
                "tool_calls_made": tool_calls_made,
                "iterations": 0,
                "latency_ms": int((time.perf_counter() - started_at) * 1000),
            }

        # Add user message
        messages.append({"role": "user", "content": message})

        # Daily report: use two-phase approach (DeepSeek-safe)
        if self._is_daily_report(message):
            return await self._two_phase_chat(messages, started_at, tool_calls_made)

        # Pre-route strong write intents (bypass LLM for write tool selection)
        pre_route = self._pre_route_write_intent(message, user_id)
        if pre_route is not None:
            pre_route["latency_ms"] = int((time.perf_counter() - started_at) * 1000)
            return pre_route

        # ReAct loop
        for iteration in range(MAX_REACT_ITERATIONS):
            tool_schemas = self.registry.get_tool_schemas()

            try:
                response = await self._call_llm_with_tools(messages, tool_schemas)
            except Exception as e:
                log.exception("llm_call_failed iteration=%d", iteration)
                return {
                    "answer": "🎀 哎呀，Kitty 的脑子有点转不过来啦～请稍后再试哦！",
                    "tool_calls_made": tool_calls_made,
                    "iterations": iteration + 1,
                    "latency_ms": int((time.perf_counter() - started_at) * 1000),
                }

            # Check for tool calls
            tool_calls = self._extract_tool_calls(response)

            if not tool_calls:
                # No tool calls — return final response
                return {
                    "answer": response.get("content", ""),
                    "tool_calls_made": tool_calls_made,
                    "iterations": iteration + 1,
                    "latency_ms": int((time.perf_counter() - started_at) * 1000),
                }

            # Separate read and write tool calls
            read_calls = []
            write_call = None

            for tc in tool_calls:
                name = tc.get("function", {}).get("name", "")
                if self.registry.is_write_tool(name):
                    write_call = tc
                    break  # Only handle one write at a time
                else:
                    read_calls.append(tc)

            # Execute read tools in parallel
            if read_calls:
                read_results = await self.registry.execute_read_tools(read_calls)

                for r in read_results:
                    tool_calls_made.append(
                        f"read:{next(tc['function']['name'] for tc in read_calls if tc.get('id') == r.get('tool_call_id'))}"
                    )

                if single_round:
                    # Single-round: return tool results directly without follow-up LLM call
                    tool_outputs = "\n\n".join(
                        r.get("content", "") for r in read_results
                    )
                    return {
                        "answer": tool_outputs,
                        "tool_calls_made": tool_calls_made,
                        "iterations": iteration + 1,
                        "latency_ms": int((time.perf_counter() - started_at) * 1000),
                    }

                # Wrap tool results as user context + synthesize with plain LLM
                # (DeepSeek API rejects tool_calls format in message history,
                #  so we avoid the native multi-turn pattern and use text-only synthesis)
                tool_outputs = "\n\n".join(
                    f"[{r.get('tool_call_id', '')[:8]}] {r.get('content', '')}"
                    for r in read_results
                )
                messages.append({
                    "role": "user",
                    "content": (
                        f"系统已为你检索了以下辅助信息：\n\n"
                        f"{tool_outputs}\n\n"
                        f"请综合这些信息，用Kitty的语气给用户一个完整、专业、温暖的回答。"
                        f"不要只是罗列信息，要结合用户的问题给出个性化建议。"
                    ),
                })

                try:
                    final_response = await self._call_llm(messages)
                except Exception:
                    log.exception("react_synthesis_failed")
                    final_response = tool_outputs

                return {
                    "answer": final_response,
                    "tool_calls_made": tool_calls_made,
                    "iterations": iteration + 1,
                    "latency_ms": int((time.perf_counter() - started_at) * 1000),
                }

            # Handle write tool — needs confirmation
            if write_call:
                func_info = write_call.get("function", {})
                write_name = func_info.get("name", "")
                write_args = func_info.get("arguments", {})
                if isinstance(write_args, str):
                    try:
                        write_args = json.loads(write_args)
                    except json.JSONDecodeError:
                        write_args = {}

                # Store as pending — ask user to confirm
                self.registry.set_pending(write_name, write_args)

                tool_calls_made.append(f"pending:{write_name}")
                return {
                    "answer": self._build_confirmation_message(write_name, write_args),
                    "tool_calls_made": tool_calls_made,
                    "iterations": iteration + 1,
                    "latency_ms": int((time.perf_counter() - started_at) * 1000),
                    "needs_confirmation": True,
                    "pending_tool": write_name,
                }

        # Max iterations reached
        return {
            "answer": "🎀  Kitty 想了好久还是想不明白～请换个方式问我吧！",
            "tool_calls_made": tool_calls_made,
            "iterations": MAX_REACT_ITERATIONS,
            "latency_ms": int((time.perf_counter() - started_at) * 1000),
        }

    # ── Helpers ────────────────────────────────────────────

    def _is_daily_report(self, message: str) -> bool:
        """Check if message contains daily report data for analysis."""
        return ("日报" in message or "健康数据" in message) and "建议" in message

    async def _two_phase_chat(
        self,
        messages: list[dict[str, Any]],
        started_at: float,
        tool_calls_made: list[str],
    ) -> dict[str, Any]:
        """Two-phase chat: Phase 1 (LLM+tools→decide), Phase 2 (plain LLM→synthesize).

        Phase 1 calls the LLM with tools to decide what to retrieve;
        Phase 2 feeds the tool results back into a plain completion
        call for synthesis. The two-phase pattern is used for daily
        reports to ensure a polished synthesized response rather than
        raw tool output.
        """
        # Phase 1: LLM decides which tools to call
        tool_schemas = self.registry.get_tool_schemas()
        try:
            response = await self._call_llm_with_tools(messages, tool_schemas)
        except Exception:
            log.exception("two_phase_llm_failed phase=1")
            return {
                "answer": "🎀 Kitty 遇到了一点小问题～请稍后再试哦！",
                "tool_calls_made": tool_calls_made,
                "iterations": 0,
                "latency_ms": int((time.perf_counter() - started_at) * 1000),
            }

        tool_calls = self._extract_tool_calls(response)

        if not tool_calls:
            # No tools needed — just return the LLM response
            return {
                "answer": response.get("content", ""),
                "tool_calls_made": tool_calls_made,
                "iterations": 1,
                "latency_ms": int((time.perf_counter() - started_at) * 1000),
            }

        # Execute read tools and collect results
        read_results = await self.registry.execute_read_tools(tool_calls)
        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "unknown")
            tool_calls_made.append(f"read:{name}")

        tool_outputs = "\n\n".join(
            f"[{r.get('tool_call_id', '')[:8]}] {r.get('content', '')}"
            for r in read_results
        )

        # Phase 2: Plain LLM call to synthesize (no tools → DeepSeek safe)
        # Use 'user' role so the LLM treats tool results as additional context
        messages.append({
            "role": "user",
            "content": (
                f"系统已经为你检索了以下辅助信息来帮助分析日报：\n\n"
                f"{tool_outputs}\n\n"
                f"请基于用户的日报数据和上述检索结果，用Kitty的语气给出个性化、专业、温暖的健康建议。"
            ),
        })

        try:
            final_response = await self._call_llm(messages)
        except Exception:
            log.exception("two_phase_llm_failed phase=2")
            final_response = tool_outputs  # Fallback: return raw tool results

        return {
            "answer": final_response,
            "tool_calls_made": tool_calls_made,
            "iterations": 2,
            "latency_ms": int((time.perf_counter() - started_at) * 1000),
        }

    def _is_confirmation(self, message: str) -> bool:
        """Check if message is a confirmation of a pending action."""
        msg = message.strip().lower()
        confirmations = {"确认", "好的", "可以", "行", "yes", "ok", "confirm", "好", "嗯", "对", "是的", "没错", "执行"}
        return any(msg == c or msg.startswith(c) for c in confirmations) and len(msg) <= 10

    def _pre_route_write_intent(self, message: str, user_id: str) -> dict[str, Any] | None:
        """Detect strong write intents and pre-route to the correct write tool directly.

        This bypasses the LLM for write tool selection, ensuring that
        update/remove operations are correctly routed even with models
        that have a "read-before-write" bias (e.g. DeepSeek).

        Returns a confirmation-result dict if a write intent is detected,
        or None to fall through to normal LLM routing.
        """
        msg = message.strip()

        # Strong update patterns
        update_patterns = [
            r"(?:把|将|帮我).{0,10}(?:改成|修改|更新|改一下|换成|换成|调整|变更).{0,20}(?:剂量|用量|频率|次数|药品|药物)",
            r"(?:改成|修改|更新|调整|变更).{0,10}(?:剂量|用量|频率|次数|mg|毫克|片|粒)",
            r"(?:剂量|用量|频率).{0,5}(?:改成|修改|更新|调整为)",
            r"(?:改成|修改|更新|换成|调整).{0,10}(?:缓释|片剂|胶囊|混悬液|口服)",
        ]
        import re
        for pat in update_patterns:
            if re.search(pat, msg):
                return self._build_direct_pending("update_medication", msg, user_id)

        # Strong remove patterns
        remove_patterns = [
            r"(?:删掉|删除|移除|不用.{0,2}了|停掉|去掉|取消|别吃.{0,2}了)",
            r"(?:把|将).{0,10}(?:删掉|删除|移除|停掉|去掉)",
        ]
        for pat in remove_patterns:
            if re.search(pat, msg):
                return self._build_direct_pending("remove_medication", msg, user_id)

        # Strong add patterns
        add_patterns = [
            r"(?:添加|加上|新增|帮我加|帮加|加到|帮我添加|加一个|加个).{0,20}(?:阿莫西林|布洛芬|二甲双胍|维生素|头孢|青霉素|药|药品|药物|\d+mg|\d+片|\d+粒)",
            r"(?:新开|开了一个).{0,10}(?:药|药品|药物).{0,10}(?:帮.{0,5}记|加|添)",
            r"(?:加|添加|新增|帮我加|帮加).{0,5}(?:一个|个|一下).{0,10}(?:药|药品|每天|每次|一天|\d+mg)",
            # Catch "记录一下用药", "帮我记录一下用药", "记录用药" etc.
            r"(?:记录|记一下|帮我记).{0,10}(?:药|药品|药物|用药)",
        ]
        for pat in add_patterns:
            if re.search(pat, msg):
                return self._build_direct_pending("add_medication", msg, user_id)

        # Strong log_health patterns
        log_patterns = [
            r"(?:记录一下|记一下|记一笔|记录|帮我记录).{0,10}(?:今天|昨天|今早|早上|下午|晚上)?(?:血压|血糖|体重|体温|心率|体脂|血氧)",
            r"(?:血压|血糖|体重|体温|心率|体脂|血氧).{0,30}(?:记录一下|记一下|记一笔|记录|帮我记录)",
        ]
        for pat in log_patterns:
            if re.search(pat, msg):
                return self._build_direct_pending("log_health", msg, user_id)

        # Strong remember patterns
        remember_patterns = [
            r"^记住.{2,30}",
            r"^帮我记一下.{2,30}",
        ]
        for pat in remember_patterns:
            if re.search(pat, msg):
                return self._build_direct_pending("remember", msg, user_id)

        # Strong medication knowledge queries (dose/side-effect questions)
        med_knowledge_patterns = [
            r"(?:一次|每次|一天|每天).{0,5}(?:吃|服用|用).{0,5}(?:多少|几|什么)",
            r"(?:怎么|如何).{0,5}(?:吃|服用|用).{0,5}(?:药|药品|药物)",
            r"(?:副作用|不良反应|禁忌|注意).{0,5}(?:有|是|什么|哪些)",
        ]
        # Only pre-route if NOT already matching write patterns
        for pat in med_knowledge_patterns:
            if re.search(pat, msg) and not any(kw in msg for kw in ["添加", "删除", "改成", "记录", "记住", "记一下"]):
                # Don't pre-route - let LLM handle, but add hint
                pass  # These are soft hints, let LLM decide

        return None

    def _build_direct_pending(self, tool_name: str, message: str, user_id: str) -> dict[str, Any] | None:
        """Build a pending confirmation response directly without LLM call."""
        started_at = time.perf_counter()
        args = {"user_id": user_id}

        # Extract reasonable default args from message
        if tool_name == "update_medication":
            import re as _re
            dose_match = _re.search(r"(\d+)\s*(?:mg|毫克|g|克|IU|国际单位)", message)
            if dose_match:
                args["dosage"] = dose_match.group(0)
            freq_match = _re.search(r"(?:每天|每日|一天)\s*(?:[一二三1-9]|一次|两次|三次)", message)
            if freq_match:
                args["frequency"] = freq_match.group(0)
        elif tool_name == "add_medication":
            import re as _re
            name_match = _re.search(r"(?:添加|加上|新增|加到|帮我加|帮加)(.{2,15}?)(?:，|,|每天|每次|一天|\d|$)", message)
            if name_match:
                args["name"] = name_match.group(1).strip()

        self.registry.set_pending(tool_name, args)

        return {
            "answer": self._build_confirmation_message(tool_name, args),
            "tool_calls_made": [f"pending:{tool_name}"],
            "iterations": 0,
            "latency_ms": int((time.perf_counter() - started_at) * 1000),
            "needs_confirmation": True,
            "pending_tool": tool_name,
        }

    def _build_confirmation_message(self, tool_name: str, args: dict[str, Any]) -> str:
        """Build a user-friendly confirmation message."""
        name_map = {
            "add_medication": f"添加药品「{args.get('name', '')}」",
            "update_medication": f"修改药品 (ID: {args.get('med_id', '')})",
            "remove_medication": f"删除药品 (ID: {args.get('med_id', '')})",
            "log_health": f"记录健康数据",
            "remember": f"记住「{args.get('fact', '')[:50]}」",
        }
        action_desc = name_map.get(tool_name, f"执行 {tool_name} 操作")

        return (
            f"🎀 Kitty 想确认一下：你要我{action_desc}，对吗？\n\n"
            f"请回复「确认」来执行，或告诉我你想怎么调整～"
        )

    async def _call_llm(self, messages: list[dict[str, Any]]) -> str:
        """Simple LLM call without tools."""
        settings = self._settings
        providers = settings.get_active_llm_providers()
        if not providers:
            return "🎀 Kitty 暂时无法连接大脑～请稍后再试！"

        p = providers[0]
        try:
            resp = await acompletion(
                model=p["model"],
                messages=messages,
                api_key=p["api_key"],
                api_base=p.get("api_base"),
                temperature=0.7,
                max_tokens=2048,
                timeout=settings.llm_request_timeout_seconds,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            log.exception("simple_llm_call_failed")
            return f"🎀 Kitty 遇到了一点小问题：{e}"

    async def _call_llm_with_tools(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """LLM call with tool definitions, returns raw message dict."""
        settings = self._settings
        providers = settings.get_active_llm_providers()
        if not providers:
            raise RuntimeError("No LLM providers configured")

        p = providers[0]
        resp = await acompletion(
            model=p["model"],
            messages=messages,
            api_key=p["api_key"],
            api_base=p.get("api_base"),
            temperature=0.7,
            max_tokens=2048,
            timeout=settings.llm_request_timeout_seconds,
            tools=tools,
            tool_choice="auto",
        )

        msg = resp.choices[0].message
        return {
            "content": msg.content or "",
            "tool_calls": msg.tool_calls if hasattr(msg, 'tool_calls') and msg.tool_calls else None,
        }

    def _extract_tool_calls(self, response: dict[str, Any]) -> list[dict[str, Any]] | None:
        """Extract tool calls from LLM response into a normalized list."""
        raw = response.get("tool_calls")
        if not raw:
            return None

        tool_calls = []
        for tc in raw:
            # litellm returns ChatCompletionMessageToolCall objects
            if hasattr(tc, 'model_dump'):
                tc_dict = tc.model_dump()
            elif isinstance(tc, dict):
                tc_dict = tc
            else:
                continue

            # Normalize: ensure function.arguments is dict, not string
            func = tc_dict.get("function", {})
            args = func.get("arguments", {})
            if isinstance(args, str):
                try:
                    func["arguments"] = json.loads(args)
                except json.JSONDecodeError:
                    func["arguments"] = {}

            tool_calls.append({
                "id": tc_dict.get("id", ""),
                "type": "function",
                "function": func,
            })

        return tool_calls if tool_calls else None
