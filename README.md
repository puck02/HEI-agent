# HEI-agent — AI 健康管家

> **v3.0 Naive Agent Mode** — 单 Agent + ReAct + 12 Tools  
> 简洁、可控、可测试的 AI 健康助手后端

[![Architecture](https://img.shields.io/badge/Architecture-ReAct%20%2B%20Tools-blue)]()
[![Benchmark](https://img.shields.io/badge/Benchmark-83.4%2F100-green)]()
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109%2B-teal)]()

---

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│              HEI-agent (FastAPI, Port 8000)               │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   ┌─────────────────────────────────────────────────┐   │
│   │              ChatAgent (ReAct Loop)              │   │
│   │                                                 │   │
│   │  while not done:                                │   │
│   │    response = llm.chat(messages, tools)         │   │
│   │    if tool_calls:                               │   │
│   │      读 Tool → 并行执行                          │   │
│   │      写 Tool → 串行 + 用户确认                   │   │
│   │    else: return response                        │   │
│   └──────────────┬──────────────────────────────────┘   │
│                  │                                       │
│   ┌──────────────┼──────────────┐                       │
│   ▼              ▼              ▼                       │
│  Read Tools    Write Tools    Tool Registry             │
│  (7 个)        (5 个)         ─ 并行/串行调度          │
│                  │              ─ 确认机制              │
│   ┌──────────────┴──────────────────────┐               │
│   │           Service Layer             │  ← 单点入口   │
│   │  medication / health_log /          │               │
│   │  knowledge  / memory               │               │
│   └──────┬──────────────┬──────────────┘               │
│          │              │                               │
│   ┌──────▼──────┐ ┌─────▼──────┐                       │
│   │   Qdrant    │ │   SQLite   │                       │
│   │ RAG + 记忆  │ │  业务数据  │                       │
│   └─────────────┘ └────────────┘                       │
└─────────────────────────────────────────────────────────┘
```

**核心理念**：一个聊天 Agent，LLM 自行判断意图 → 调用对应 Tool → 返回结果。Agent Tool 和 API endpoint 走同一个 Service 层，数据一致。

---

## Tool 清单（12 个）

### 读 Tool（并行执行，无副作用）

| Tool | 说明 | 数据源 |
|------|------|--------|
| `search_health` | 检索健康知识 | Qdrant `health_knowledge` |
| `search_medication` | 检索药品信息 | Qdrant `medication_info` |
| `search_tcm` | 检索中医知识 | Qdrant `tcm_wellness` |
| `search_memory` | 检索长期记忆 | Qdrant + BM25 + RRF + Rerank |
| `describe_image` | 图片识别 | DashScope Vision（TODO） |
| `get_my_medications` | 查询在服药品 | SQLite |
| `get_health_logs` | 查询健康打卡 | SQLite |

### 写 Tool（串行执行 + 用户确认）

| Tool | 说明 |
|------|------|
| `add_medication` | 添加药品（需确认） |
| `update_medication` | 修改药品（需确认） |
| `remove_medication` | 删除药品（需确认） |
| `log_health` | 记录健康数据（需确认） |
| `remember` | 写入长期记忆 |

---

## 记忆系统：混合检索

```
search_memory(query)
  │
  ├── ① Qdrant 语义检索    → Top 20
  ├── ② BM25 关键词检索    → Top 20
  │
  ├── ③ RRF 合并去重       → ~15 条
  └── ④ DashScope Rerank   → Top 5
```

---

## 项目结构

```
HEI-agent/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── config.py                  # 配置
│   ├── database.py                # SQLite
│   │
│   ├── agent/                     # ⭐ Agent 层（v3 核心）
│   │   ├── chat_agent.py          # ReAct while 循环
│   │   ├── tool_registry.py       # 12 Tools 注册 + 调度
│   │   └── tools/                 # 12 个 Tool 实现
│   │       ├── knowledge.py       # search_health/med/tcm
│   │       ├── medication.py      # 用药 CRUD
│   │       ├── health_log.py      # 健康日志
│   │       ├── memory_tool.py     # search_memory/remember
│   │       └── vision.py          # describe_image
│   │
│   ├── services/                  # ⭐ 统一数据层（v3 新增）
│   │   ├── medication_service.py  # SQLite CRUD
│   │   ├── health_log_service.py  # 健康日志读写
│   │   ├── knowledge_service.py   # RAG 封装
│   │   └── memory_service.py      # 混合检索管线
│   │
│   ├── rag/                       # RAG 引擎（复用）
│   ├── llm/                       # LiteLLM 路由器
│   ├── api/v1/                    # REST API
│   │   ├── chat.py                # 对话接口 → ChatAgent
│   │   ├── health.py              # 健康接口 → Service
│   │   ├── medication.py          # 用药接口 → Service
│   │   └── sessions.py            # 会话管理
│   └── schemas/                   # Pydantic 模型
│
├── demo-frontend/                 # Vue.js 演示前端
├── tests/                         # 测试套件
│   ├── run_benchmark.sh           # 一键测试脚本
│   ├── benchmark_runner.py        # 测试引擎
│   ├── test_data/                 # 125+ 测试用例
│   └── benchmarks/                # 历史报告
├── data/knowledge/                # 知识库源文件
└── docs/                          # 设计文档
```

---

## 技术栈

| 组件 | 选型 |
|------|------|
| LLM | DeepSeek（LiteLLM 路由） |
| Agent 框架 | 原生 Python ReAct 循环 |
| 向量数据库 | Qdrant（Docker） |
| 业务数据库 | SQLite |
| Embedding | DashScope API |
| Rerank | DashScope Rerank API |
| BM25 | `rank-bm25` |
| API 框架 | FastAPI |
| 前端 | Vue.js 3 + Vite |

---

## 快速开始（Demo 模式）

Demo 模式仅需 Qdrant + LLM API key，无需 PostgreSQL/Redis/JWT。

### 1. 环境配置

```bash
cp .env.example .env
# 编辑 .env，配置：
#   DEMO_MODE=true
#   DEEPSEEK_API_KEY=sk-xxx
#   DASHSCOPE_API_KEY=sk-xxx
#   QDRANT_URL=http://localhost:6333
```

### 2. 启动 Qdrant

```bash
docker run -d -p 6333:6333 qdrant/qdrant
```

### 3. 导入知识库

```bash
python scripts/ingest_knowledge.py --demo
```

### 4. 启动后端

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 5. 启动前端

```bash
cd demo-frontend && npm install && npm run dev -- --host 0.0.0.0 --port 5173
```

### 访问

| 地址 | 说明 |
|------|------|
| `http://localhost:5173` | 前端页面 |
| `http://localhost:8000/health` | 健康检查 |
| `http://localhost:8000/docs` | Swagger API 文档 |

---

## 确认机制

写操作需要用户确认：

```
用户: "帮我删除阿莫西林"

Agent:
  ① get_my_medications() → 查出阿莫西林 id=3
  ② 回复: "确认删除 [阿莫西林 每天3次]？"

用户: "确认"

Agent:
  ③ remove_medication(id=3) → 执行
  ④ 回复: "已删除 ✅"
```

---

## Benchmark 指标

| 指标 | 结果 | 测试规模 |
|------|------|----------|
| RAG Recall@3 | 78.9% | 57 条查询 |
| Tool 调用准确率 | 80.6% | 36 条消息 |
| 端到端延迟 P95 | 5.3s | 10 次测量 |
| 混合检索 Recall@5 | 100% | 20 记忆 + 10 查询 |
| 确认机制正确率 | 100% | 15 个写操作 |
| **总体评分** | **83.4/100 🟢** | |

```bash
# 一键运行全部测试
bash tests/run_benchmark.sh all
```

---

## 重构历程

| 版本 | 分支 | 架构 |
|------|------|------|
| v1 | `main` | LangGraph Multi-Agent + Pipeline + ContextAssembler |
| v3 | `naive-agent-mode` | **单 Agent + ReAct + 12 Tools + Service Layer** |

---

## License

MIT
