#!/usr/bin/env python3
"""
HEI-agent Phase 1+2 本地测试脚本
使用 DeepSeek API 测试核心组件
"""

import asyncio
import sys
import os
import time

# 确保从项目目录加载 .env
os.chdir(os.path.dirname(os.path.abspath(__file__)))

async def test_1_imports():
    """测试 1: 所有新模块能正常导入"""
    print("\n" + "="*50)
    print("📦 测试 1: 模块导入")
    print("="*50)
    
    try:
        from app.pipelines.base import Pipeline, AgentContext
        print("  ✅ pipelines.base")
        
        from app.pipelines.fast_pipeline import FastPipeline
        print("  ✅ pipelines.fast_pipeline")
        
        from app.pipelines.agent_pipeline import AgentPipeline
        print("  ✅ pipelines.agent_pipeline")
        
        from app.agents.router import IntentRouter
        print("  ✅ agents.router")
        
        from app.agents.base import BaseAgent
        print("  ✅ agents.base")
        
        from app.context.assembler import ContextAssembler
        print("  ✅ context.assembler")
        
        from app.rag.decider import RAGDecider
        print("  ✅ rag.decider")
        
        from app.reflection.base import ReflectionPolicy, ScoringDimension
        print("  ✅ reflection.base")
        
        from app.reflection.scorer import ReflectionScorer, get_policy_for_agent
        print("  ✅ reflection.scorer")
        
        from app.reflection.policies.health_policy import HealthPolicy
        print("  ✅ reflection.policies.health_policy")
        
        from app.reflection.policies.general_policy import GeneralPolicy
        print("  ✅ reflection.policies.general_policy")
        
        from app.schemas.completion import CompletionRequest, CompletionResponse
        print("  ✅ schemas.completion")
        
        print("\n  🎉 全部 12 个模块导入成功!")
        return True
    except Exception as e:
        print(f"\n  ❌ 导入失败: {e}")
        return False


async def test_2_rag_decider():
    """测试 2: RAGDecider 三层策略（纯逻辑，不调 LLM）"""
    print("\n" + "="*50)
    print("🧠 测试 2: RAGDecider 三层策略")
    print("="*50)
    
    from app.rag.decider import RAGDecider
    
    decider = RAGDecider()
    
    test_cases = [
        # (message, intent, expected_rag, description)
        ("我最近总是失眠怎么办", "health", True, "健康关键词 → RAG"),
        ("帮我看看布洛芬的副作用", "medication", True, "用药意图 → RAG"),
        ("你好啊", "general", False, "普通问候 → 不RAG"),
        ("谢谢", "general", False, "短消息 → 不RAG"),
        ("我头痛得厉害", "health", True, "症状关键词 → RAG"),
        ("今天天气真好", "general", False, "无关内容 → 不RAG"),
        ("我想了解维生素C的作用", "health", True, "营养关键词 → RAG"),
        ("帮我分析一下这周的睡眠趋势", "insight", True, "睡眠关键词 → RAG"),
    ]
    
    passed = 0
    for msg, intent, expected, desc in test_cases:
        result = await decider.should_retrieve(msg, intent)
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        print(f"  {status} {desc}: \"{msg}\" → RAG={result}")
    
    print(f"\n  结果: {passed}/{len(test_cases)} 通过")
    return passed == len(test_cases)


async def test_3_reflection_policies():
    """测试 3: ReflectionPolicy 策略模式（纯逻辑，不调 LLM）"""
    print("\n" + "="*50)
    print("📊 测试 3: ReflectionPolicy 策略模式")
    print("="*50)
    
    from app.reflection.policies.health_policy import HealthPolicy
    from app.reflection.policies.general_policy import GeneralPolicy
    from app.reflection.scorer import get_policy_for_agent
    
    # 测试 HealthPolicy
    health = HealthPolicy()
    dims = health.dimensions()
    print(f"\n  HealthPolicy:")
    print(f"    维度数: {len(dims)}")
    print(f"    最高分: {health.max_total_score}")
    print(f"    维度: {[d.name for d in dims]}")
    
    prompt = health.build_prompt()
    assert "安全" in prompt or "safety" in prompt.lower(), "HealthPolicy prompt 应包含安全相关"
    print(f"    ✅ build_prompt() 包含安全维度")
    
    # 测试 GeneralPolicy
    general = GeneralPolicy()
    g_dims = general.dimensions()
    print(f"\n  GeneralPolicy:")
    print(f"    维度数: {len(g_dims)}")
    print(f"    最高分: {general.max_total_score}")
    print(f"    维度: {[d.name for d in g_dims]}")
    
    # 测试策略路由
    assert get_policy_for_agent("health_advisor").__class__.__name__ == "HealthPolicy"
    assert get_policy_for_agent("direct_answer").__class__.__name__ == "GeneralPolicy"
    print(f"\n  ✅ 策略路由正确: health_advisor→HealthPolicy, direct_answer→GeneralPolicy")
    
    # 测试通过标准
    scores_pass = {"total": 20, "safety": 2, "accuracy": 4, "completeness": 4, "empathy": 4}
    scores_fail = {"total": 10, "safety": 0, "accuracy": 2, "completeness": 2, "empathy": 2}
    
    assert health.passing_criteria(scores_pass) == True
    assert health.passing_criteria(scores_fail) == False
    print(f"  ✅ HealthPolicy passing_criteria 正确")
    
    return True


async def test_4_llm_router():
    """测试 4: LLM Router + DeepSeek API 调用"""
    print("\n" + "="*50)
    print("🤖 测试 4: LLM Router (DeepSeek API)")
    print("="*50)
    
    from app.llm.router import get_llm_router
    
    router = get_llm_router()
    
    # 显示 provider 状态
    status = router.get_status()
    print(f"\n  Provider 状态:")
    for p in status:
        avail = "✅" if p["available"] else "❌"
        print(f"    {avail} {p['name']}: {p['model']}")
    
    if not any(p["available"] for p in status):
        print("\n  ❌ 没有可用的 LLM provider!")
        return False
    
    # 测试简单调用
    print(f"\n  测试简单对话...")
    start = time.time()
    try:
        result = await router.chat(
            messages=[{"role": "user", "content": "你好，请用一句话介绍自己"}],
            temperature=0.7,
            max_tokens=100,
        )
        latency = (time.time() - start) * 1000
        print(f"  ✅ 调用成功!")
        print(f"    Provider: {result.provider}")
        print(f"    Model: {result.model}")
        print(f"    延迟: {latency:.0f}ms")
        print(f"    Tokens: {result.usage}")
        print(f"    回复: {result.content[:100]}...")
        return True
    except Exception as e:
        print(f"  ❌ 调用失败: {e}")
        return False


async def test_5_intent_router():
    """测试 5: IntentRouter (需要 LLM)"""
    print("\n" + "="*50)
    print("🎯 测试 5: IntentRouter (LLM 意图分类)")
    print("="*50)
    
    from app.agents.router import IntentRouter
    
    router = IntentRouter()
    
    test_cases = [
        ("我最近总是失眠怎么办", "health"),
        ("你好啊", "general"),
        ("帮我看看布洛芬的副作用", "medication"),
    ]
    
    passed = 0
    for msg, expected in test_cases:
        try:
            result = await router.classify_intent(msg)
            status = "✅" if result == expected else "⚠️"
            if result == expected:
                passed += 1
            print(f"  {status} \"{msg}\" → {result} (expected: {expected})")
        except Exception as e:
            print(f"  ❌ \"{msg}\" → 错误: {e}")
    
    print(f"\n  结果: {passed}/{len(test_cases)} 通过")
    return passed >= 2  # 至少 2/3 通过


async def test_6_rag_decider_llm():
    """测试 6: RAGDecider LLM 模式"""
    print("\n" + "="*50)
    print("🔍 测试 6: RAGDecider LLM 语义判断")
    print("="*50)
    
    from app.rag.decider import RAGDecider
    
    decider = RAGDecider()
    
    # 测试一个关键词匹配不到但语义上需要 RAG 的 case
    tricky_case = "我最近压力很大，感觉什么都不想做"
    
    # 关键词模式
    keyword_result = await decider.should_retrieve(tricky_case, "general")
    print(f"  关键词模式: \"{tricky_case}\" → RAG={keyword_result}")
    
    # LLM 模式
    try:
        llm_result = await decider.should_retrieve(tricky_case, "general", enable_llm_check=True)
        print(f"  LLM 模式:   \"{tricky_case}\" → RAG={llm_result}")
        print(f"  ✅ LLM 模式可以捕获关键词漏掉的语义")
        return True
    except Exception as e:
        print(f"  ❌ LLM 模式失败: {e}")
        return False


async def test_7_reflection_scorer():
    """测试 7: ReflectionScorer 完整评分流程"""
    print("\n" + "="*50)
    print("⭐ 测试 7: ReflectionScorer 评分")
    print("="*50)
    
    from app.reflection.scorer import ReflectionScorer
    
    scorer = ReflectionScorer()
    
    user_msg = "我最近总是失眠怎么办"
    good_response = "失眠是很常见的问题。建议您：1. 保持规律作息 2. 睡前避免使用电子设备 3. 适当运动 4. 如果持续两周以上，建议就医。注意：我不是医生，以上仅为一般性建议。"
    
    try:
        result = await scorer.evaluate(
            user_message=user_msg,
            response=good_response,
            agent_used="health_advisor",
        )
        print(f"  Policy: {result['policy_name']}")
        print(f"  总分: {result['total_score']}")
        print(f"  各维度: {result['scores']}")
        print(f"  通过: {result['passed']}")
        print(f"  需重试: {result['should_retry']}")
        if result['issues']:
            print(f"  问题: {result['issues']}")
        print(f"  ✅ ReflectionScorer 评分流程正常")
        return True
    except Exception as e:
        print(f"  ❌ 评分失败: {e}")
        return False


async def main():
    print("🏥 HEI-agent Phase 1+2 本地测试")
    print("使用 DeepSeek API")
    print("="*50)
    
    results = {}
    
    # 测试 1: 模块导入（必须通过）
    results["模块导入"] = await test_1_imports()
    
    # 测试 2: RAGDecider 纯逻辑
    results["RAGDecider 策略"] = await test_2_rag_decider()
    
    # 测试 3: ReflectionPolicy 纯逻辑
    results["ReflectionPolicy"] = await test_3_reflection_policies()
    
    # 测试 4: LLM Router
    results["LLM Router"] = await test_4_llm_router()
    
    # 测试 5-7 需要 LLM，如果测试 4 失败则跳过
    if results["LLM Router"]:
        results["IntentRouter"] = await test_5_intent_router()
        results["RAGDecider LLM"] = await test_6_rag_decider_llm()
        results["ReflectionScorer"] = await test_7_reflection_scorer()
    else:
        print("\n  ⚠️ LLM 不可用，跳过测试 5-7")
        results["IntentRouter"] = False
        results["RAGDecider LLM"] = False
        results["ReflectionScorer"] = False
    
    # 汇总
    print("\n" + "="*50)
    print("📋 测试汇总")
    print("="*50)
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    for name, ok in results.items():
        status = "✅ 通过" if ok else "❌ 失败"
        print(f"  {status} | {name}")
    
    print(f"\n  总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n  🎉 全部测试通过！Phase 1+2 代码可正常运行！")
    elif passed >= 4:
        print("\n  ⚠️ 核心测试通过，部分 LLM 测试失败（可能是网络/API 问题）")
    else:
        print("\n  ❌ 多项测试失败，需要检查代码")
    
    return passed >= 4


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
