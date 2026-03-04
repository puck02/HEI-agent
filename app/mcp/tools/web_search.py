"""
Web search tool — limited-scope health information search.

Uses DuckDuckGo Instant Answer API (no key required) as default.
Can be replaced with SerpAPI by setting SEARCH_API_KEY.
"""

from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger(__name__)


async def web_search(query: str) -> str:
    """
    Search for health-related information on the web.
    Returns a summary of top results.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # DuckDuckGo Instant Answer API
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            results = []

            # Abstract (main result)
            if data.get("Abstract"):
                results.append(f"📖 {data['Abstract']}")
                if data.get("AbstractSource"):
                    results.append(f"  来源: {data['AbstractSource']}")

            # Related topics
            related = data.get("RelatedTopics", [])
            for topic in related[:3]:
                if isinstance(topic, dict) and "Text" in topic:
                    results.append(f"• {topic['Text']}")

            # Answer (if direct answer available)
            if data.get("Answer"):
                results.insert(0, f"✅ {data['Answer']}")

            if results:
                return "\n".join(results)
            else:
                return f"未找到关于「{query}」的直接结果。建议咨询专业医生获取准确信息。"

    except httpx.TimeoutException:
        return "搜索超时，请稍后再试。"
    except Exception as e:
        log.warning("web_search_error", query=query, error=str(e))
        return f"搜索失败: {e}"
