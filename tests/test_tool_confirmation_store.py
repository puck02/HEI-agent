import pytest

from app.agent.tool_registry import ToolRegistry
from app.agent.tooling import PendingAction, InMemoryPendingActionStore


@pytest.mark.asyncio
async def test_pending_actions_are_isolated_by_user_and_session():
    store = InMemoryPendingActionStore()

    await store.set(PendingAction(
        user_id="user_a",
        session_id="session_1",
        tool_name="add_medication",
        args={"name": "布洛芬"},
    ))
    await store.set(PendingAction(
        user_id="user_a",
        session_id="session_2",
        tool_name="log_health",
        args={"data": "血压 120/80"},
    ))
    await store.set(PendingAction(
        user_id="user_b",
        session_id="session_1",
        tool_name="remember",
        args={"fact": "对青霉素过敏"},
    ))

    first = await store.get("user_a", "session_1")
    second = await store.get("user_a", "session_2")
    third = await store.get("user_b", "session_1")

    assert first is not None
    assert first.tool_name == "add_medication"
    assert first.args == {"name": "布洛芬"}
    assert second is not None
    assert second.tool_name == "log_health"
    assert third is not None
    assert third.tool_name == "remember"


@pytest.mark.asyncio
async def test_pending_action_replaces_existing_action_in_same_user_session():
    store = InMemoryPendingActionStore()

    await store.set(PendingAction(
        user_id="demo_user",
        session_id="s1",
        tool_name="add_medication",
        args={"name": "布洛芬"},
    ))
    await store.set(PendingAction(
        user_id="demo_user",
        session_id="s1",
        tool_name="add_medication",
        args={"name": "阿莫西林"},
    ))

    pending = await store.get("demo_user", "s1")

    assert pending is not None
    assert pending.args == {"name": "阿莫西林"}


@pytest.mark.asyncio
async def test_clearing_pending_action_only_affects_one_user_session():
    store = InMemoryPendingActionStore()
    await store.set(PendingAction("user", "s1", "remember", {"fact": "喜欢早睡"}))
    await store.set(PendingAction("user", "s2", "remember", {"fact": "喜欢散步"}))

    removed = await store.clear("user", "s1")

    assert removed is not None
    assert removed.args == {"fact": "喜欢早睡"}
    assert await store.get("user", "s1") is None
    assert (await store.get("user", "s2")).args == {"fact": "喜欢散步"}


def test_tool_registry_uses_registered_metadata_for_write_policy():
    registry = ToolRegistry()

    async def fake_tool():
        return "ok"

    registry.register(
        name="custom_write_tool",
        func=fake_tool,
        description="Custom write tool",
        parameters={"type": "object", "properties": {}},
        is_write=True,
    )
    registry.register(
        name="custom_read_tool",
        func=fake_tool,
        description="Custom read tool",
        parameters={"type": "object", "properties": {}},
        is_write=False,
    )

    assert registry.is_write_tool("custom_write_tool") is True
    assert registry.is_write_tool("custom_read_tool") is False
    assert registry.is_write_tool("missing_tool") is False
