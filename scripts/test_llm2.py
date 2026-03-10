"""Quick test: does increasing max_tokens fix the empty content issue?"""
import asyncio
from litellm import acompletion
from app.config import get_settings

async def test():
    s = get_settings()
    model = f"openai/{s.glm_model}"
    
    # Test with max_tokens=4096 instead of 800
    print("=== max_tokens=4096 ===")
    resp = await acompletion(
        model=model,
        messages=[
            {"role": "system", "content": "你是Kitty健康管家。"},
            {"role": "user", "content": "我最近身体不太舒服"}
        ],
        temperature=0.7,
        max_tokens=4096,
        api_key=s.glm_api_key,
        api_base=s.glm_base_url,
    )
    msg = resp.choices[0].message
    print(f"content len: {len(msg.content) if msg.content else 0}")
    print(f"content: {repr(msg.content[:200]) if msg.content else 'EMPTY'}")
    r = getattr(msg, 'reasoning_content', None)
    if r is None:
        try:
            d = msg.model_dump()
            r = d.get('reasoning_content') or d.get('provider_specific_fields', {}).get('reasoning_content')
        except:
            pass
    r_len = len(r) if r else 0
    print(f"reasoning len: {r_len}")
    print(f"usage: total={resp.usage.total_tokens}, reasoning={resp.usage.completion_tokens_details.reasoning_tokens if resp.usage.completion_tokens_details else 'N/A'}")

    # Test 2: Health with context
    print("\n=== max_tokens=4096, with health context ===")
    resp2 = await acompletion(
        model=model,
        messages=[
            {"role": "system", "content": "你是Kitty健康管家。"},
            {"role": "system", "content": "用户健康数据: 步数3000步，睡眠7小时，体重70kg。用药：布洛芬、阿莫西林。"},
            {"role": "user", "content": "分析一下我的健康状况"}
        ],
        temperature=0.7,
        max_tokens=4096,
        api_key=s.glm_api_key,
        api_base=s.glm_base_url,
    )
    msg2 = resp2.choices[0].message
    print(f"content len: {len(msg2.content) if msg2.content else 0}")
    print(f"content: {repr(msg2.content[:300]) if msg2.content else 'EMPTY'}")
    print(f"usage: total={resp2.usage.total_tokens}")

    # Test 3: 你觉得我的身体有什么潜在的隐患吗
    print("\n=== max_tokens=4096, potential health risks ===")
    resp3 = await acompletion(
        model=model,
        messages=[
            {"role": "system", "content": "你是Kitty健康管家。"},
            {"role": "user", "content": "你觉得我的身体有什么潜在的隐患吗"}
        ],
        temperature=0.7,
        max_tokens=4096,
        api_key=s.glm_api_key,
        api_base=s.glm_base_url,
    )
    msg3 = resp3.choices[0].message
    print(f"content len: {len(msg3.content) if msg3.content else 0}")
    print(f"content: {repr(msg3.content[:300]) if msg3.content else 'EMPTY'}")
    print(f"usage: total={resp3.usage.total_tokens}")

asyncio.run(test())
