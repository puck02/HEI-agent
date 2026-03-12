import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest

from app.api.v1 import chat as chat_module
from app.schemas.chat import ChatRequest


class _FakeShortTerm:
    def __init__(self):
        self.messages = []

    async def register_session(self, _user_id: str, _session_id: str):
        return None

    async def add_message(self, session_id: str, role: str, content: str):
        self.messages.append((session_id, role, content))

    async def get_formatted_history(self, _session_id: str, **_kwargs):
        return "用户: 你好\n助手: 你好呀"


class _FakeMemoryManager:
    def __init__(self):
        self.short_term = _FakeShortTerm()

    async def recall(self, **_kwargs):
        return {"relevant_memories": ["最近鼻塞评分较高"]}

    async def extract_and_store_insights(self, **_kwargs):
        return None


class _FakeRag:
    async def retrieve_as_context(self, **_kwargs):
        return "可用温热蒸汽缓解鼻塞"


@pytest.mark.asyncio
async def test_run_chat_pipeline_returns_timing_and_trace(monkeypatch):
    async def _fake_run_chat(**_kwargs):
        return {
            "response": "这里是回答",
            "agent_used": "kitty_chat",
            "model_used": "glm-4.7-flashx",
            "tools_called": ["memory_recall"],
        }

    monkeypatch.setattr(chat_module, "get_memory_manager", lambda: _FakeMemoryManager())
    monkeypatch.setattr(chat_module, "get_rag_engine", lambda: _FakeRag())
    monkeypatch.setattr(chat_module, "run_chat", _fake_run_chat)
    monkeypatch.setattr(chat_module, "_build_health_context", lambda *_args, **_kwargs: asyncio.sleep(0, result="健康上下文"))
    monkeypatch.setattr(chat_module, "_build_medication_context", lambda *_args, **_kwargs: asyncio.sleep(0, result="用药上下文"))

    req = ChatRequest(message="最近鼻塞严重怎么办", session_id="s-test")
    user = SimpleNamespace(id=uuid.uuid4())

    result = await chat_module._run_chat_pipeline(
        req=req,
        current_user=user,
        db=object(),
        session_id="s-test",
    )

    assert result["answer"] == "这里是回答"
    assert result["response_time_ms"] is not None
    assert result["response_time_ms"] >= 0
    assert len(result["trace"]) >= 3
    assert any(item["stage"] == "context_ready" for item in result["trace"])
    assert any(item["stage"] == "llm_done" for item in result["trace"])


@pytest.mark.asyncio
async def test_run_chat_pipeline_timeout_fallback(monkeypatch):
    async def _slow_run_chat(**_kwargs):
        await asyncio.sleep(0.01)
        return {"response": "never"}

    async def _fake_wait_for(_awaitable, timeout):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(chat_module, "get_memory_manager", lambda: _FakeMemoryManager())
    monkeypatch.setattr(chat_module, "run_chat", _slow_run_chat)
    monkeypatch.setattr(chat_module, "_build_health_context", lambda *_args, **_kwargs: asyncio.sleep(0, result=""))
    monkeypatch.setattr(chat_module, "_build_medication_context", lambda *_args, **_kwargs: asyncio.sleep(0, result=""))
    monkeypatch.setattr(chat_module.asyncio, "wait_for", _fake_wait_for)

    req = ChatRequest(message="你好", session_id="s-timeout")
    user = SimpleNamespace(id=uuid.uuid4())

    result = await chat_module._run_chat_pipeline(
        req=req,
        current_user=user,
        db=object(),
        session_id="s-timeout",
    )

    assert result["agent_used"] == "timeout_fallback"
    assert "请再问我一次" in result["answer"]
    assert result["response_time_ms"] >= 0
    assert any(item["stage"] == "timeout" for item in result["trace"])


@pytest.mark.asyncio
async def test_chat_stream_emits_progress_then_done(monkeypatch):
    async def _fake_pipeline(req, current_user, db, session_id, progress_cb=None):
        if progress_cb:
            await progress_cb({"stage": "start", "message": "开始处理请求", "elapsed_ms": 1})
            await progress_cb({"stage": "context_ready", "message": "上下文加载完成", "elapsed_ms": 5})
        return {
            "answer": "最终答案",
            "session_id": session_id,
            "agent_used": "kitty_chat",
            "model_used": "glm-4.7-flashx",
            "response_time_ms": 25,
            "trace": [],
        }

    monkeypatch.setattr(chat_module, "_run_chat_pipeline", _fake_pipeline)

    req = ChatRequest(message="测试流式")
    user = SimpleNamespace(id=uuid.uuid4())

    response = await chat_module.chat_stream(req=req, current_user=user, db=object())

    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    combined = "".join(chunks)
    assert "event: progress" in combined
    assert "event: done" in combined
    assert "最终答案" in combined

    done_lines = [line for line in combined.split("\n") if line.startswith("data: ")]
    done_payload = json.loads(done_lines[-1][6:])
    assert done_payload["response_time_ms"] == 25