"""Vision tool using DashScope Qwen-VL for image description."""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


async def describe_image(image_url: str) -> str:
    """Call the DashScope Vision API to describe an image and return the description text."""
    settings = get_settings()
    api_key = settings.dashscope_api_key
    if not api_key:
        return "Image description failed: dashscope_api_key is not configured."

    body = {
        "model": "qwen-vl-plus",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": "请详细描述这张图片的内容，包括文字、物体、场景等。"},
                ],
            }
        ],
        "max_tokens": 500,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        log.exception("vision_api_http_error")
        return f"Image description failed: {e}"
    except Exception:
        log.exception("vision_api_unexpected_error")
        return "Image description failed due to an internal error."

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        log.error("vision_api_unexpected_response", data=data)
        return f"Image description failed: unexpected response format ({e})"
