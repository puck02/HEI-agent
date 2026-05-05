# HEI-agent Naive Agent Mode — 重构计划

> 分支: `naive-agent-mode` | 日期: 2026-05-04

---

## 1. 目标

将当前 LangGraph 多 Agent 架构重构为 **单 Agent + ReAct + Tools** 的简洁架构。

**核心理念**: 一个聊天 Agent，LLM 自行判断意图 → 调用对应 Tool → 返回结果 → 继续推理 / 生成回复。

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    ChatAgent (ReAct)                      │
│                                                          │
│  while not done:                                         │
│    response = llm.chat(messages + system_prompt, tools)  │
│    if tool_calls:                                        │
│      读 Tool → 并行执行                                   │
│      写 Tool → 串行 + 用户确认                             │
│      results → append to messages                        │
│    else: return response                                 │
└──────────────┬──────────────────────────────────────────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
  Tool 1    Tool 2    Tool 3     (读:并发 | 写:串行+确认)

               │
    ┌──────────┴──────────────────────────┐
    │           Service Layer              │  ← 单点数据入口
    │  medication_service / health_log /   │
    │  knowledge_service / memory_service  │
    └──────┬───────────────┬──────────────┘
           │               │
    ┌──────▼──────┐  ┌─────▼──────┐
    │  Qdrant     │  │  SQLite    │
    │  RAG + 记忆  │  │  User/Med  │
    └─────────────┘  └────────────┘
```

**关键约束**: Chat Agent 的 Tool 和 Health/Med API endpoint 走**同一个 Service 层**，确保对话界面、日报界面、用药界面数据一致。

---

## 3. Tool 清单（12 个）

### 读 Tool（并行执行，无副作用）

| Tool | 参数 | 返回 | 数据源 |
|------|------|------|--------|
| `search_health` | `query: str` | 相关健康知识片段 + 引用 | Qdrant(health) |
| `search_medication` | `query: str` | 相关药品知识片段 + 引用 | Qdrant(medication) |
| `search_tcm` | `query: str` | 相关中医知识片段 + 引用 | Qdrant(tcm) |
| `search_memory` | `query: str` | Top 5 相关长期记忆 | Qdrant(memory) |
| `describe_image` | `image_url: str` | 图片文字描述 | DashScope Vision |
| `get_my_medications` | — | 当前在服药品列表 | SQLite |
| `get_health_logs` | `days: int = 7` | 近 N 天健康打卡记录 | SQLite |

### 写 Tool（串行执行 + 用户确认）

| Tool | 参数 | 操作 | 联动 |
|------|------|------|------|
| `add_medication` | `name, dosage, frequency, ...` | INSERT | → 用药界面立即可见 |
| `update_medication` | `id, field, value` | UPDATE | → 用药界面立即可见 |
| `remove_medication` | `id` | DELETE | → 用药界面立即消失 |
| `log_health` | `data` | INSERT | → 日报/洞察立即可见 |
| `remember` | `fact: str` | 写入长期记忆 @ Qdrant | — |

---

## 4. 确认流程

写操作需要用户确认后再执行：

```
用户: "帮我把阿莫西林删了"

Agent:
  ① tool: get_my_medications()                    ← 查出阿莫西林 id=3
  ② 回复: "确认删除 [阿莫西林 每天3次每次1粒]？"    ← 不执行删除

用户: "确认"

Agent:
  ③ tool: remove_medication(id=3)                  ← 真正执行
  ④ 回复: "已删除阿莫西林 ✅"
```

增/删/改都需要确认，确认提示由 LLM 生成（包含操作详情）。

---

## 5. 长期记忆模块

### 存储: Qdrant

```
collection: user_memories
  id: uuid
  content: 原始记忆文本
  type: 自由 tag（health_record / medication / allergy / preference / ...）
  importance: 0.0~1.0
  entity_tags: ["阿莫西林", "过敏", "青霉素"]
  created_at: timestamp
```

### 检索: 混合检索 + RRF + Rerank

```
search_memory(query)
  │
  ├── ① Embedding 语义检索 (Qdrant)  → Top 20
  ├── ② BM25 关键词检索 (内存索引)    → Top 20
  │
  ├── ③ RRF 合并去重                  → ~15 条
  └── ④ DashScope Rerank API          → Top 5
```

### 写入: remember(fact)

```
store(content)
  → LLM API embed(content)              ← DashScope embedding
  → Qdrant.upsert(id, vector, payload)
  → 更新 BM25 内存索引
```

### 压缩: cron job（后续）

超过 6 个月的旧记忆 → LLM 压缩摘要 → 替换原文 → 重新 embed。

---

## 6. RAG 知识库（复用，不改）

| 集合 | 来源 | 文件数 |
|------|------|--------|
| `health_knowledge` | data/knowledge/health/ | 12 |
| `medication_info` | data/knowledge/medication/ | 5 |
| `tcm_wellness` | data/knowledge/tcm/ | 12(含7PDF) |

Tool 层面的 `search_*` 去引用的 Qdrant 就是现成的。

---

## 7. 多模态支持

`describe_image(image_url)` — 当前只做图片识别：

```
用户发图片 → describe_image(url) → Vision API → 文字描述 → Agent 理解
```

**未来扩展**: LLM 直接接收多模态消息时，消息格式从纯文本改为 `[{type: text}, {type: image_url}]`，不需要改 ReAct 循环。

---

## 8. 文件结构

```
app/
├── agent/
│   ├── __init__.py
│   ├── chat_agent.py           # ReAct while 循环
│   ├── tool_registry.py        # 注册 + 并行/串行调度 + 确认机制
│   └── tools/
│       ├── __init__.py
│       ├── knowledge.py        # search_health / search_med / search_tcm
│       ├── medication.py       # CRUD 用药
│       ├── health_log.py       # get_health_logs / log_health
│       ├── memory_tool.py      # search_memory / remember
│       └── vision.py           # describe_image
├── services/                   # ★ 新建: 统一数据层
│   ├── __init__.py
│   ├── medication_service.py   # add/update/remove/get_all
│   ├── health_log_service.py   # get_logs/log_health
│   ├── knowledge_service.py    # RAG 封装
│   └── memory_service.py       # 混合检索 (Qdrant + BM25 + RRF + Rerank)
├── api/v1/
│   ├── chat.py                 # ★ 改: 调 ChatAgent
│   ├── health.py               # ★ 改: 调 health_log_service
│   ├── medication.py           # ★ 改: 调 medication_service
│   └── sessions.py             # 不改
├── rag/                        # 不改
├── memory/                     # → memory_service.py 替代
├── context/                    # → 移除或精简
├── agents/                     # → 移除 (health_advisor/medication_agent/insight_analyst)
├── pipelines/                  # → 移除 (FastPipeline/AgentPipeline)
└── llm/                        # ★ 精简: 只保留 LLM 调用客户端
```

---

## 9. 实施步骤

| 步骤 | 内容 | 状态 |
|------|------|------|
| 1 | 创建 `app/services/` 数据层 | ⬜ |
| 2 | 实现 `memory_service.py`（混合检索） | ⬜ |
| 3 | 实现 `app/agent/tool_registry.py` | ⬜ |
| 4 | 实现 12 个 Tool | ⬜ |
| 5 | 实现 `chat_agent.py`（ReAct 循环） | ⬜ |
| 6 | 改造 `api/v1/chat.py` → ChatAgent | ⬜ |
| 7 | 改造 `api/v1/health.py` → service | ⬜ |
| 8 | 改造 `api/v1/medication.py` → service | ⬜ |
| 9 | 清理旧代码（agents/pipelines/context） | ⬜ |
| 10 | 全链路测试（对话 + 日报 + 用药三界面联调） | ⬜ |

---

## 10. 技术栈

| 组件 | 选型 |
|------|------|
| LLM | DashScope / MiMo-v2.5-pro |
| 向量库 | Qdrant (已有 Docker 容器) |
| 业务库 | SQLite |
| Embedding | DashScope API |
| Rerank | DashScope Rerank API |
| BM25 | `rank-bm25` (纯 Python) |
| Vision | DashScope Vision API |
| 框架 | FastAPI + 原生 Python while 循环 |
