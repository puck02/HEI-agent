# HEI-agent 全链路 Benchmark 测试说明报告

> 主题：解释简历中“全链路 Benchmark 得分 82.5/100，覆盖 RAG Recall、Tool 准确率、Memory Recall、P95 延迟、确认机制”等指标的测试设计、代码路径、评分口径和面试讲法。

---

## 1. 结论概览

当前 HEI-agent 的 Benchmark Runner 位于：

```text
tests/benchmark_runner.py
```

它不是单纯测某一个接口，而是围绕健康管家核心链路设计了 5 类指标：

| 指标 | 目标 | 当前报告结果 |
|---|---|---:|
| RAG Recall@3 | 测知识库检索能否召回正确资料 | 78.9% |
| Tool Accuracy | 测 ReAct Agent 是否选对工具 | 75.0% |
| E2E Latency P95 | 测端到端响应耗时 | 4992.96ms，约 5.0s |
| Memory Recall@5 | 测长期记忆能否被召回 | 100.0% |
| Confirmation Mechanism | 测写操作是否触发确认 | 100.0% |
| Overall Score | 加权总分 | 82.5/100 |

> 注意：你提到的“Tool 准确率 77.8%、P95 延迟 5.3s”可以理解为简历/历史口径的近似表达；当前仓库 `tests/results/report.md` 里实际记录是 Tool 75.0%、P95 4992.96ms（约 5.0s）。正式面试建议以当前报告文件为准，或者口头说“约 75%～78%”“P95 约 5s”。

---

## 2. 为什么叫“全链路 Benchmark”？

这个 benchmark 覆盖了健康管家的关键运行路径：

```text
用户问题
  ↓
ChatAgent / ReAct Loop
  ↓
工具选择：RAG / 用药 / 记忆 / 健康日志 / 确认机制
  ↓
外部存储：Qdrant / SQLite / SessionStore
  ↓
LLM 综合回答
  ↓
统计召回率、工具准确率、延迟、确认率
```

它测的不是单个模型回答“看起来好不好”，而是把项目中最关键的工程能力拆成了可量化指标：

1. **能不能查到知识**：RAG Recall；
2. **能不能选对工具**：Tool Accuracy；
3. **能不能记住用户事实**：Memory Recall；
4. **响应够不够快**：P95 Latency；
5. **写操作安不安全**：Confirmation Mechanism。

---

## 3. Benchmark 入口与运行方式

脚本说明：

```text
tests/benchmark_runner.py
```

脚本顶部定义了使用方式：

```bash
python tests/benchmark_runner.py [metric|all]
```

支持单项或全量：

```text
all     — run all 5 metrics
rag     — RAG Recall@3
tool    — Tool Accuracy
latency — E2E Latency
memory  — Hybrid Search Recall@5
confirm — Confirmation Mechanism
```

输出目录：

```text
tests/results/
```

核心输出文件：

```text
tests/results/report.md
tests/results/rag_recall_results.json
tests/results/tool_accuracy_results.json
tests/results/latency_results.json
tests/results/memory_recall_results.json
tests/results/confirmation_results.json
```

---

## 4. 指标一：RAG Recall@3

### 4.1 测试目的

RAG Recall@3 用来衡量：

> 给定一个健康/药品/中医问题，系统从对应知识库中返回的 Top 3 结果里，是否包含期望关键词。

这里测的是“检索召回”，不是最终回答质量。

### 4.2 测试数据

测试集在：

```text
tests/test_data/rag_queries.json
```

每条样本包含：

```json
{
  "query": "高血压患者饮食要注意什么？",
  "collection": "health",
  "expected_answer_keywords": ["低盐", "钠", "蔬菜", "水果", "钾"],
  "difficulty": "easy"
}
```

字段含义：

| 字段 | 含义 |
|---|---|
| `query` | 用户问题 |
| `collection` | 目标知识库，health / medication / tcm |
| `expected_answer_keywords` | 期望召回内容中应出现的关键词 |
| `difficulty` | easy / medium / hard / boundary |

### 4.3 代码逻辑

核心函数：

```python
async def test_rag_recall() -> dict[str, Any]:
```

知识库映射：

```python
collection_map = {
    "health": KnowledgeService.search_health,
    "medication": KnowledgeService.search_medication,
    "tcm": KnowledgeService.search_tcm,
}
```

每个 query 会调用对应搜索函数：

```python
raw = await search_func(query)
```

然后只检查 Top 3：

```python
for line in lines[:3]:
    if check_keywords(line, keywords):
        hit = True
        break
```

### 4.4 当前结果

当前报告：

| 知识库 | 问题数 | 命中数 | Recall@3 |
|---|---:|---:|---:|
| health_knowledge | 22 | 17 | 77.3% |
| medication_info | 17 | 13 | 76.5% |
| tcm_wellness | 18 | 15 | 83.3% |
| 总计 | 57 | 45 | 78.9% |

### 4.5 如何解释这个指标

面试可以说：

> RAG Recall@3 是我用来评估知识库召回能力的指标。测试集覆盖健康、药品、中医三类知识库，每个问题预先配置期望关键词。系统检索 Top 3 chunk，只要其中任意结果包含期望关键词，就算命中。当前总计 57 个问题，命中 45 个，Recall@3 为 78.9%。

---

## 5. 指标二：Tool Accuracy

### 5.1 测试目的

Tool Accuracy 用来衡量：

> ReAct Agent 面对不同用户意图时，是否选择了正确的工具。

这对 Agent 项目很重要，因为健康管家不是单纯聊天，它要在多个工具之间路由：

```text
search_health
search_medication
search_tcm
search_memory
get_my_medications
get_health_logs
describe_image
add_medication
update_medication
remove_medication
log_health
remember
```

### 5.2 测试数据

测试集在：

```text
tests/test_data/tool_intents.json
```

样例：

```json
{
  "message": "阿莫西林一次吃多少？",
  "expected_tool": "search_medication",
  "expected_confirmation": false
}
```

写操作样例：

```json
{
  "message": "帮我把阿莫西林加到我的药品清单里，每天三次每次500mg",
  "expected_tool": "add_medication",
  "expected_confirmation": true
}
```

### 5.3 代码逻辑

核心函数：

```python
async def test_tool_accuracy() -> dict[str, Any]:
```

它创建一个 ChatAgent：

```python
agent = ChatAgent()
```

然后对每条 message 执行：

```python
resp = await agent.chat(user_id, session_id, message, single_round=True)
```

`single_round=True` 的含义是：

> 只测试首轮工具选择，不要求完整多轮综合回答。

然后从返回值中取：

```python
tool_calls = resp.get("tool_calls_made", [])
needs_conf = resp.get("needs_confirmation", False)
pending_tool = resp.get("pending_tool", "")
```

判断 actual_tool：

```python
if tc.startswith("pending:"):
    actual_tool = tc.replace("pending:", "")
elif tc.startswith("read:"):
    actual_tool = tc.replace("read:", "")
```

### 5.4 精确匹配与部分匹配

精确匹配：

```python
exact = actual_tool == expected_tool
```

代码里还允许“写工具被读工具替代”作为部分匹配：

```python
read_write_pairs = {
    "add_medication": "get_my_medications",
    "update_medication": "get_my_medications",
    "remove_medication": "get_my_medications",
    "log_health": "get_health_logs",
    "remember": "search_memory",
}
```

不过当前结果里 partial 是 0。

### 5.5 当前结果

当前报告：

```text
总计 36 条
exact_matches = 27
partial_matches = 0
accuracy = 75.0%
```

表述为：

| 测试数 | 正确数 | Tool 准确率 |
|---:|---:|---:|
| 36 | 27 | 75.0% |

### 5.6 当前主要错误类型

报告里记录的部分错误：

| 用户输入 | 期望工具 | 实际工具 |
|---|---|---|
| 阿莫西林一次吃多少？ | search_medication | get_my_medications |
| 我有点头疼，不知道是不是感冒了 | search_health | get_my_medications |
| 昨天吃了阿莫西林感觉胃不舒服，正常吗 | search_medication | search_memory |
| 帮我看看最近血糖记录情况 | get_health_logs | log_health |
| 这张B超单子能帮我读一下吗 | describe_image | None |

### 5.7 如何解释这个指标

面试可以说：

> Tool Accuracy 是为了验证 ReAct Agent 的工具路由能力。测试集覆盖读工具、写工具、视觉工具和纯聊天场景。每条样本都有 expected_tool，运行 ChatAgent 单轮工具选择后，比较实际工具和期望工具。当前 36 条样本中 27 条工具选择正确，准确率 75%。错误主要集中在药品知识问题和个人用药记录问题边界不清，以及无图片输入时视觉工具不会触发。

如果要使用用户提到的简历口径，可以说：

> 工具准确率约 75%～78%，当前报告文件记录为 75.0%。

---

## 6. 指标三：E2E Latency / P95 延迟

### 6.1 测试目的

Latency 测的是端到端耗时：

```text
用户消息进入 ChatAgent
  ↓
LLM / 工具调用 / 单轮结果返回
  ↓
统计耗时
```

它反映 demo 的用户体验。

### 6.2 测试类别

代码中分三类：

```python
queries = {
    "rag": [
        "高血压怎么预防？",
        "阿莫西林的副作用是什么？",
        "枸杞有什么好处？",
        "每天应该运动多久？",
    ],
    "tool": [
        "帮我查一下我现在在吃什么药",
        "看看我最近的健康记录",
        "搜索一下我的过敏历史",
    ],
    "chitchat": [
        "你好呀Kitty",
        "今天天气怎么样？",
        "你有什么功能？",
    ],
}
```

### 6.3 统计方式

每条样本用：

```python
t0 = time.perf_counter()
resp = await agent.chat(user_id, f"{session_id}_{category}", msg, single_round=True)
latency_ms = (time.perf_counter() - t0) * 1000
```

然后计算：

```python
p50 = sorted_lat[int(n * 0.5)]
p95 = sorted_lat[min(int(n * 0.95), n - 1)]
p99 = sorted_lat[min(int(n * 0.99), n - 1)]
mean = sum(sorted_lat) / n
```

> 注意：当前样本量只有 10 条，所以这里的 P95 更接近“样本高位延迟”，不是严格生产环境大样本 P95。

### 6.4 当前结果

当前报告：

| 类别 | P50 | P95 | P99 | 均值 | 样本数 |
|---|---:|---:|---:|---:|---:|
| rag | 2539.88ms | 3062.1ms | 3062.1ms | 2398.64ms | 4 |
| tool | 1310.3ms | 1386.86ms | 1386.86ms | 1322.54ms | 3 |
| chitchat | 2729.67ms | 4992.96ms | 4992.96ms | 3210.62ms | 3 |
| 总体 | 2288.73ms | 4992.96ms | 4992.96ms | 2319.4ms | 10 |

可以对外简洁表述为：

```text
P95 约 5s
```

如果使用你的简历口径：

```text
P95 延迟约 5.3s
```

更稳妥：

```text
P95 延迟约 5s 左右
```

### 6.5 如何解释这个指标

面试可以说：

> 延迟测试覆盖 RAG 查询、工具查询和闲聊三类场景。每条请求从进入 ChatAgent 到返回结果计算耗时，最后统计 P50、P95、P99。当前 10 条样本总体 P95 约 5 秒。这个数据主要用于 demo 阶段的体验评估，不是大规模压测；后续如果做生产压测，需要扩大样本量并区分冷启动、模型调用、向量检索和工具执行耗时。

---

## 7. 指标四：Memory Recall@5

### 7.1 测试目的

Memory Recall@5 用来评估长期记忆系统能否召回用户事实。

这里测的是：

```text
写入一组用户长期记忆
  ↓
用问题查询这些记忆
  ↓
Top 5 结果中是否包含期望关键词
```

### 7.2 测试数据

记忆种子：

```text
tests/test_data/memory_seeds.json
```

查询集：

```text
tests/test_data/memory_queries.json
```

查询样例：

```json
{
  "query": "用户对什么药物过敏？",
  "expected_memory_keywords": ["青霉素", "皮疹", "呼吸困难"]
}
```

### 7.3 代码逻辑

核心函数：

```python
async def test_memory_recall() -> dict[str, Any]:
```

先写入记忆：

```python
await service.remember(
    user_id=user_id,
    content=seed["content"],
    memory_type=seed.get("type", "general"),
    importance=seed.get("importance", 0.5),
)
```

再查询：

```python
results = await service.search_memory(
    keywords=search_kw,
    user_id=user_id,
    top_k=5,
)
```

检查 Top 5 里是否出现期望关键词：

```python
for r in results[:5]:
    content = r.get("content", "")
    if check_keywords(content, expected_kw):
        hit = True
        break
```

### 7.4 当前结果

当前报告：

```text
写入记忆数: 20/20
查询数: 10
命中数: 10
Recall@5: 100.0%
```

查询覆盖：

- 用户对什么药物过敏；
- 用户有什么运动习惯；
- 用户在吃什么药；
- 用户家族有什么遗传病史；
- 用户睡眠情况；
- 最近体检结果；
- 海鲜过敏症状；
- BMI；
- 饮食偏好；
- 住院史。

### 7.5 重要说明：当前 Memory Recall 实际是 SQLite 关键词召回

`benchmark_runner.py` 的报告文本写了：

```text
混合检索(Qdrant+BM25+RRF+Rerank)
纯Qdrant向量检索
```

但结合当前代码，`test_memory_recall()` 实际调用的是：

```python
MemoryService.search_memory()
```

而 `MemoryService` 的实现是 SQLite `LIKE` 关键词搜索，不是 Qdrant/BM25/RRF/Rerank。

所以面试时建议谨慎表述为：

> Memory Recall@5 当前测的是 SQLite 长期记忆的关键词召回能力，10 个查询全部命中。报告模板里“混合检索”的表述是早期命名残留，当前代码实际走的是 MemoryService 的 SQLite 搜索。

这个说法非常重要，能避免被追问“你的记忆向量检索代码在哪里”。

---

## 8. 指标五：确认机制正确率

### 8.1 测试目的

确认机制测试用于验证：

> 对用药增删改、健康日志写入、长期记忆写入等有副作用的操作，系统是否先要求用户确认，而不是直接执行。

健康场景里，这个指标很关键，因为写操作涉及用户数据安全。

### 8.2 测试数据

测试集在：

```text
tests/test_data/confirmation_scenarios.json
```

样例：

```json
{
  "message": "帮我添加阿莫西林，每天三次，一次500mg",
  "expected_tool": "add_medication",
  "should_confirm": true
}
```

覆盖的写操作包括：

```text
add_medication
update_medication
remove_medication
log_health
remember
```

### 8.3 代码逻辑

核心函数：

```python
async def test_confirmation() -> dict[str, Any]:
```

每条样本执行：

```python
resp = await agent.chat(user_id, f"{session_id}_{results['total']}", message, single_round=True)
needs_conf = resp.get("needs_confirmation", False)
pending_tool = resp.get("pending_tool", "")
```

只要返回 `needs_confirmation=True`，就认为确认机制触发成功：

```python
if needs_confirmation := needs_conf:
    results["confirmed"] += 1
else:
    results["skipped"] += 1
```

### 8.4 当前结果

当前报告：

```text
总计 15
确认 15
确认机制正确率 100.0%
```

### 8.5 为什么确认机制能做到 100%？

当前 `ChatAgent` 里有一层强规则预路由：

```python
pre_route = self._pre_route_write_intent(message, user_id)
if pre_route is not None:
    return pre_route
```

它用正则识别强写入意图：

- 添加药品；
- 修改药品；
- 删除药品；
- 记录健康数据；
- 记住某个事实。

一旦识别到写操作，就不会直接执行工具，而是进入 pending：

```python
self.registry.set_pending(tool_name, args)
```

然后返回确认消息：

```python
return {
    "answer": self._build_confirmation_message(tool_name, args),
    "tool_calls_made": [f"pending:{tool_name}"],
    "needs_confirmation": True,
    "pending_tool": tool_name,
}
```

所以确认机制不是完全依赖模型“自觉”，而是通过代码层 hard routing 做了兜底。

### 8.6 如何解释这个指标

面试可以说：

> 确认机制测试覆盖 15 条写操作，包括添加/修改/删除用药、记录健康数据和写入长期记忆。测试判断标准是首轮响应是否返回 `needs_confirmation=True` 和 pending tool。当前 15 条全部触发确认，确认机制正确率 100%。这说明对有副作用的操作，系统不会直接写数据库，而是先进入 pending 状态，等待用户确认。

---

## 9. Overall Score 82.5/100 是怎么算的？

`benchmark_runner.py` 中的评分权重：

```python
# RAG 25%, Tool 25%, Latency(inverse) 15%, Memory 20%, Confirm 15%
latency_score = max(0, min(100, 100 - max(0, (lat_p95 - 1000) / 100)))
overall = (
    rag_score * 0.25
    + tool_accuracy * 0.25
    + latency_score * 0.15
    + mem_recall * 0.20
    + conf_rate * 0.15
)
```

权重表：

| 指标 | 权重 |
|---|---:|
| RAG Recall@3 | 25% |
| Tool 准确率 | 25% |
| 延迟反向分 | 15% |
| Memory Recall@5 | 20% |
| 确认机制 | 15% |

延迟分数公式：

```text
latency_score = 100 - max(0, (P95 - 1000) / 100)
```

含义：

- P95 <= 1000ms，延迟分接近 100；
- P95 每超过 100ms，扣 1 分；
- 分数限制在 0～100。

以当前报告 P95=4992.96ms 为例：

```text
latency_score = 100 - (4992.96 - 1000) / 100
              ≈ 60.07
```

综合：

```text
RAG: 78.9 * 0.25 = 19.725
Tool: 75.0 * 0.25 = 18.75
Latency: 60.07 * 0.15 ≈ 9.01
Memory: 100.0 * 0.20 = 20.0
Confirm: 100.0 * 0.15 = 15.0
Total ≈ 82.49 → 82.5
```

所以：

```text
总体评分 = 82.5/100
```

---

## 10. 这个 Benchmark 的价值

这个 benchmark 的价值在于，它不是只展示“模型能回答问题”，而是把 Agent 系统拆成了多个可验证环节：

| 能力 | 对应指标 |
|---|---|
| 知识库是否能召回正确资料 | RAG Recall@3 |
| Agent 是否会选工具 | Tool Accuracy |
| 长期记忆是否能召回 | Memory Recall@5 |
| 服务响应是否能接受 | P95 Latency |
| 写操作是否安全 | Confirmation Mechanism |

这对于简历和面试很有用，因为它能体现你不是只做了一个 demo 页面，而是有意识地做了：

```text
评测集设计
指标定义
自动化 benchmark runner
原始结果落盘
报告生成
错误案例分析
```

---

## 11. 当前 Benchmark 的边界

面试时也要知道边界，避免被问穿。

### 11.1 样本量不大

Latency 只有 10 条样本，所以 P95 是 demo 阶段体验指标，不是生产级压测。

可以说：

> 这个 P95 是小样本 benchmark 的高位延迟，用于 demo 阶段对比和回归，不是大规模生产压测。

### 11.2 Tool Accuracy 受模型影响

Tool 选择依赖 LLM 的 function calling 能力和 prompt，换模型后可能变化。

可以说：

> Tool Accuracy 是和模型、prompt、工具 schema 都相关的指标。我用它主要做回归测试，防止 prompt 或工具描述改动后导致路由能力下降。

### 11.3 Memory Recall 报告标题有历史命名残留

当前代码实际是 SQLite LIKE 搜索，不是 Qdrant/BM25/RRF/Rerank。

可以说：

> Memory Recall 当前评估的是长期记忆关键词召回能力，底层是 SQLite LIKE；报告模板里的“混合检索”是早期命名残留，后续应该修正文案。

### 11.4 Confirmation 测的是是否触发确认，不是完整二阶段提交

当前确认指标判断的是：首轮是否返回 `needs_confirmation=True`。

它不是完整测试：

```text
用户确认 → 真正执行写操作 → 数据库验证
```

可以说：

> 当前确认 benchmark 测的是写操作是否进入 pending 确认状态。完整数据落库验证可以作为下一阶段测试补充。

---

## 12. 面试讲法

### 12.1 完整版

> 我给 HEI-agent 做了一个全链路 Benchmark Runner，不只是看模型回答是否自然，而是把健康管家的核心能力拆成五个指标：RAG Recall、Tool Accuracy、Memory Recall、E2E Latency 和确认机制。
> RAG Recall@3 用 57 条健康、药品、中医问题测试 Top 3 检索结果是否包含期望关键词，当前是 78.9%；Tool Accuracy 用 36 条意图样本测试 ReAct Agent 是否选对工具，当前约 75%；Memory Recall@5 先写入 20 条长期记忆，再用 10 条问题测试 Top 5 是否召回，当前是 100%；确认机制用 15 条写操作测试是否进入 pending confirmation，当前是 100%；整体按 25/25/15/20/15 加权，得到 82.5/100。
> 这个 benchmark 的价值是它能做回归测试，帮我定位是知识库召回问题、工具路由问题、记忆召回问题，还是确认机制问题。

### 12.2 简短版

> Benchmark 覆盖 5 个维度：RAG Recall@3、Tool Accuracy、Memory Recall@5、P95 延迟和确认机制。当前总分 82.5/100，其中 RAG Recall 78.9%，Tool 准确率约 75%，Memory Recall 和确认机制都是 100%，P95 延迟约 5 秒。它主要用于验证 Agent 从检索、工具调用、长期记忆到安全写操作的完整链路。

### 12.3 如果面试官追问“82.5 怎么算的？”

> 我设置了权重：RAG 25%、Tool 25%、Latency 15%、Memory 20%、Confirmation 15%。延迟是反向分，P95 超过 1 秒后按每 100ms 扣 1 分。代入当前结果：RAG 78.9、Tool 75、Latency 分约 60、Memory 100、Confirmation 100，加权后约 82.5。

### 12.4 如果面试官问“这个分数可靠吗？”

> 它更适合叫 demo 阶段的自动化回归 benchmark，不是生产级大规模评测。它的价值在于测试口径固定、可以反复跑，能帮助我发现工具路由或检索召回是否退化。比如 Tool Accuracy 下降时，我能进一步看错误案例，判断是 prompt、工具 schema 还是 hard routing 需要调整。

---

## 13. 简历推荐写法

比较稳的写法：

```text
构建 benchmark_runner 自动化评测脚本，覆盖 RAG Recall@3、Tool 调用准确率、Memory Recall@5、P95 延迟和写操作确认机制 5 类指标；在 57 条 RAG 问题、36 条工具意图、20 条记忆种子和 15 条确认场景上评估，综合得分 82.5/100。
```

如果需要更短：

```text
设计全链路 Benchmark 体系，覆盖 RAG 召回、工具路由、长期记忆召回、端到端延迟和写操作确认机制，综合得分 82.5/100。
```

如果要带数字：

```text
全链路 Benchmark 得分 82.5/100：RAG Recall@3 78.9%，Tool Accuracy 约 75%，Memory Recall@5 100%，确认机制 100%，P95 延迟约 5s。
```

> 建议不要强写“Tool 77.8%、P95 5.3s”为唯一口径，除非你有对应结果文件。当前仓库结果更准确是 Tool 75.0%、P95 4992.96ms。

---

## 14. 后续可改进方向

1. **扩大样本量**：RAG 和 Tool 样本继续增加，Latency 至少跑 100+ 次；
2. **拆分延迟来源**：区分 LLM、Qdrant、SQLite、工具执行、网络耗时；
3. **修正 Memory 报告文案**：当前实际是 SQLite LIKE，不应写 Qdrant+BM25+RRF；
4. **确认机制做二阶段验证**：不仅测 pending，还测用户确认后是否正确落库；
5. **Tool Accuracy 分类别统计**：读工具、写工具、视觉工具、闲聊分别给准确率；
6. **增加失败案例分析**：自动输出高频混淆工具对，如 `search_medication` vs `get_my_medications`；
7. **引入 LLM-as-judge 但不替代规则指标**：用于回答质量评估，但核心安全指标仍保持确定性规则。

---

## 15. 一句话总结

> 这个 Benchmark 的核心意义不是追求一个漂亮分数，而是把 Agent 的 RAG、工具路由、记忆召回、延迟和安全确认拆成可重复评估的指标，让项目从“能跑的 demo”变成“有评测和回归能力的 Agent 系统”。
