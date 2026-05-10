import pytest

from app.agent.chat_agent import ChatAgent
from app.agent.tooling import PendingAction


@pytest.mark.asyncio
async def test_confirmation_executes_only_pending_action_for_current_session(monkeypatch):
    agent = ChatAgent()
    executed = []

    async def fake_execute_write_tool(tool_call):
        name = tool_call["function"]["name"]
        executed.append(name)
        return {
            "tool_call_id": tool_call["id"],
            "role": "tool",
            "content": f"executed:{name}",
        }

    async def fake_call_llm(messages):
        return "done"

    monkeypatch.setattr(agent.registry, "execute_write_tool", fake_execute_write_tool)
    monkeypatch.setattr(agent, "_call_llm", fake_call_llm)

    await agent.pending_store.set(PendingAction(
        user_id="demo_user",
        session_id="session_a",
        tool_name="add_medication",
        args={"name": "布洛芬"},
    ))
    await agent.pending_store.set(PendingAction(
        user_id="demo_user",
        session_id="session_b",
        tool_name="log_health",
        args={"data": "血压 120/80"},
    ))

    result = await agent.chat(
        user_id="demo_user",
        session_id="session_a",
        message="确认",
        conversation_history=[],
        single_round=True,
    )

    assert result["answer"].startswith("✅ 已执行 add_medication")
    assert executed == ["add_medication"]
    assert await agent.pending_store.get("demo_user", "session_a") is None
    assert (await agent.pending_store.get("demo_user", "session_b")).tool_name == "log_health"


@pytest.mark.asyncio
async def test_cancellation_clears_pending_action_without_execution(monkeypatch):
    agent = ChatAgent()
    executed = []

    async def fake_execute_write_tool(tool_call):
        executed.append(tool_call)
        return {"tool_call_id": tool_call["id"], "role": "tool", "content": "executed"}

    monkeypatch.setattr(agent.registry, "execute_write_tool", fake_execute_write_tool)

    await agent.pending_store.set(PendingAction(
        user_id="demo_user",
        session_id="session_a",
        tool_name="remember",
        args={"fact": "喜欢早睡"},
    ))

    result = await agent.chat(
        user_id="demo_user",
        session_id="session_a",
        message="取消",
        conversation_history=[],
        single_round=True,
    )

    assert executed == []
    assert await agent.pending_store.get("demo_user", "session_a") is None
    assert "取消" in result["answer"]
    assert result["tool_calls_made"] == ["cancelled:remember"]
