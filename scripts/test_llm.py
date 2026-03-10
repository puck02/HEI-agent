"""Test GLM response to diagnose empty content issue."""
import asyncio
import json
from litellm import acompletion
from app.config import get_settings

async def test():
    s = get_settings()
    print(f"Model: openai/{s.glm_model}")
    print(f"Base URL: {s.glm_base_url}")
    print("---")

    # Test 1: Simple greeting (should work)
    print("\n=== TEST 1: Simple greeting ===")
    resp1 = await acompletion(
        model=f"openai/{s.glm_model}",
        messages=[
            {"role": "system", "content": "你是Kitty健康管家。"},
            {"role": "user", "content": "你好"}
        ],
        temperature=0.7,
        max_tokens=800,
        api_key=s.glm_api_key,
        api_base=s.glm_base_url,
    )
    msg1 = resp1.choices[0].message
    print(f"content repr: {repr(msg1.content)}")
    print(f"content len: {len(msg1.content) if msg1.content else 0}")
    print(f"usage: {resp1.usage}")

    # Test 2: Health query (might fail)
    print("\n=== TEST 2: Health query ===")
    resp2 = await acompletion(
        model=f"openai/{s.glm_model}",
        messages=[
            {"role": "system", "content": "你是Kitty健康管家。"},
            {"role": "user", "content": "我最近身体不太舒服"}
        ],
        temperature=0.7,
        max_tokens=800,
        api_key=s.glm_api_key,
        api_base=s.glm_base_url,
    )
    msg2 = resp2.choices[0].message
    print(f"content repr: {repr(msg2.content)}")
    print(f"content len: {len(msg2.content) if msg2.content else 0}")
    print(f"usage: {resp2.usage}")

    # Test 3: Health query with context data
    print("\n=== TEST 3: Health query with context data ===")
    resp3 = await acompletion(
        model=f"openai/{s.glm_model}",
        messages=[
            {"role": "system", "content": "你是Kitty健康管家，负责根据用户健康数据提供建议。用户健康数据: 步数3000步，睡眠7小时。"},
            {"role": "user", "content": "分析一下我的健康状况"}
        ],
        temperature=0.7,
        max_tokens=800,
        api_key=s.glm_api_key,
        api_base=s.glm_base_url,
    )
    msg3 = resp3.choices[0].message
    print(f"content repr: {repr(msg3.content)}")
    print(f"content len: {len(msg3.content) if msg3.content else 0}")
    print(f"usage: {resp3.usage}")

    # Test 4: Check raw response object
    print("\n=== TEST 4: Raw response inspection ===")
    resp4 = await acompletion(
        model=f"openai/{s.glm_model}",
        messages=[
            {"role": "system", "content": "你是健康助手。"},
            {"role": "user", "content": "我最近身体不太舒服，帮我分析一下"}
        ],
        temperature=0.7,
        max_tokens=800,
        api_key=s.glm_api_key,
        api_base=s.glm_base_url,
    )
    msg4 = resp4.choices[0].message
    print(f"message type: {type(msg4)}")
    print(f"content: {repr(msg4.content)}")
    print(f"role: {msg4.role}")
    print(f"tool_calls: {getattr(msg4, 'tool_calls', 'N/A')}")
    print(f"refusal: {getattr(msg4, 'refusal', 'N/A')}")
    print(f"function_call: {getattr(msg4, 'function_call', 'N/A')}")
    
    # Try to get raw dict
    try:
        raw = msg4.model_dump()
        print(f"model_dump: {json.dumps(raw, ensure_ascii=False, indent=2)}")
    except Exception as e:
        print(f"model_dump failed: {e}")
    
    try:
        raw_resp = resp4.model_dump()
        print(f"\nFull response choices[0]: {json.dumps(raw_resp['choices'][0], ensure_ascii=False, indent=2)}")
    except Exception as e:
        print(f"full dump failed: {e}")

    # Test 5: Try with different model name format
    print("\n=== TEST 5: Without openai/ prefix ===")
    try:
        resp5 = await acompletion(
            model=s.glm_model,
            messages=[
                {"role": "system", "content": "你是健康助手Kitty。"},
                {"role": "user", "content": "我最近身体不太舒服"}
            ],
            temperature=0.7,
            max_tokens=800,
            api_key=s.glm_api_key,
            api_base=s.glm_base_url,
            custom_llm_provider="openai",
        )
        msg5 = resp5.choices[0].message
        print(f"content repr: {repr(msg5.content)}")
        print(f"content len: {len(msg5.content) if msg5.content else 0}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test())
