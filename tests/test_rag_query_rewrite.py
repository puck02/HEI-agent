import pytest

from app.rag import engine_qdrant
from app.llm.router import LLMCallResult


class _FakeRouter:
    def __init__(self):
        self.chat_messages = None
        self.embedded_texts = None

    async def chat(self, messages, **kwargs):
        self.chat_messages = messages
        return LLMCallResult(
            content="高血压 低盐饮食 钠摄入 控制 建议",
            model="fake-model",
            provider="fake-provider",
        )

    async def embed(self, texts):
        self.embedded_texts = texts
        return [[0.1, 0.2, 0.3]]


class _FakeQdrantClient:
    def __init__(self):
        self.query_params = None

    async def query_points(self, **kwargs):
        self.query_params = kwargs
        return type("Resp", (), {"points": []})()


@pytest.mark.asyncio
async def test_retrieve_rewrites_query_before_embedding(monkeypatch):
    router = _FakeRouter()
    client = _FakeQdrantClient()

    monkeypatch.setattr(engine_qdrant, "get_llm_router", lambda: router)

    rag = engine_qdrant.RAGEngine.__new__(engine_qdrant.RAGEngine)
    rag.client = client
    rag.top_k = 5
    rag.rerank_top_k = 20
    rag.dashscope_api_key = None
    rag._httpx = None
    rag.query_rewrite_enabled = True

    await rag.retrieve("我血压有点高，吃东西要注意啥？", collections=["health"])

    assert router.embedded_texts == ["高血压 低盐饮食 钠摄入 控制 建议"]
    assert router.chat_messages is not None
    assert "我血压有点高" in router.chat_messages[-1]["content"]
