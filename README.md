# HEl Agent — AI 健康管家后端

> HElDairy 的多 Agent 智能后端系统，基于 LangGraph 构建

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                     HElDairy Android App                        │
│  (Retrofit → Agent API, JWT auth, 数据同步)                      │
└─────────────────┬───────────────────────────────────────────────┘
                  │ HTTPS / REST
┌─────────────────▼───────────────────────────────────────────────┐
│                   FastAPI Gateway (hel-agent)                    │
│  /auth/* │ /api/v1/health/* │ /api/v1/med/* │ /api/v1/sync/*    │
├─────────────────────────────────────────────────────────────────┤
│                  LangGraph Orchestrator Agent                    │
│  (Router Agent — 意图识别 → 分发到子 Agent)                       │
├──────────┬──────────┬───────────┬────────────────────────────────┤
│ Health   │Medication│ Insight   │ MCP Tools                      │
│ Advisor  │ Agent    │ Analyst   │ (天气/搜索/计算器/数据查询)       │
├──────────┴──────────┴───────────┴────────────────────────────────┤
│              Shared Infrastructure Layer                         │
│  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌────────────────────┐     │
│  │LLM Router│ │RAG Engine│ │Memory  │ │User Data Store     │     │
│  │(LiteLLM) │ │(Qdrant)  │ │Manager │ │(PostgreSQL)        │     │
│  └─────────┘ └──────────┘ └────────┘ └────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| Agent 框架 | LangGraph ≥ 0.2.40 | 有状态图、条件路由、checkpointer |
| LLM Router | LiteLLM | DeepSeek/GLM/OpenAI 自动 failover |
| 向量数据库 | Qdrant | 多 collection RAG 知识库 |
| 关系数据库 | PostgreSQL 16 + pgvector | 用户数据、长期记忆 |
| 缓存 | Redis 7 | 短期会话记忆 |
| API 框架 | FastAPI | 异步、自动 OpenAPI 文档 |
| 认证 | JWT (PyJWT) | 多用户、无状态 |
| 工具协议 | MCP (Model Context Protocol) | 标准化工具调用 |

## 快速开始

### 1. 环境准备

```bash
cp .env.example .env
# 编辑 .env，填入至少一个 LLM provider 的 API key
```

### 2. Docker 启动

```bash
docker-compose up -d
```

这会启动 4 个服务：
- `hel-agent` — FastAPI 应用 (端口 8000)
- `hel-postgres` — PostgreSQL 16 + pgvector (端口 5432)
- `hel-redis` — Redis 7 (端口 6379)
- `hel-qdrant` — Qdrant 向量数据库 (端口 6333)

### 3. 本地开发（不用 Docker）

```bash
# 安装依赖
pip install -r requirements.txt

# 确保 PostgreSQL、Redis、Qdrant 已启动

# 初始化数据库
python scripts/init_db.py --seed

# 导入知识库
python scripts/ingest_knowledge.py

# 启动服务
uvicorn app.main:app --reload --port 8000
```

### 4. 验证

```bash
# 健康检查
curl http://localhost:8000/health

# 注册用户
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","email":"demo@test.com","password":"Demo123456"}'

# 登录获取 token
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"Demo123456"}'

# 使用 token 对话
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"我最近睡眠不太好，有什么建议吗？"}'
```

## API 文档

启动后访问 http://localhost:8000/docs 查看自动生成的 Swagger UI。

### 核心端点

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/auth/register` | 用户注册 |
| POST | `/auth/login` | 登录获取 JWT |
| POST | `/auth/refresh` | 刷新 token |
| GET  | `/auth/me` | 当前用户信息 |
| POST | `/api/v1/chat` | 统一 Agent 对话 |
| POST | `/api/v1/health/daily-advice` | 日报建议（Android 兼容） |
| POST | `/api/v1/health/follow-up` | 自适应追问（Android 兼容） |
| POST | `/api/v1/health/weekly-insight` | 周洞察（Android 兼容） |
| POST | `/api/v1/medication/parse-nlp` | 用药 NLP 解析（Android 兼容） |
| POST | `/api/v1/medication/info-summary` | 药品信息摘要 |
| POST | `/api/v1/sync/upload` | 数据同步上传 |
| GET  | `/api/v1/sync/status` | 同步状态查询 |
| GET  | `/health` | 系统健康检查 |

## Multi-Agent 系统

### 架构流程图

```
                       ┌─────────────────────────────────────────────────────────┐
                       │                  LangGraph StateGraph                   │
                       └─────────────────────────────────────────────────────────┘
                                                │
                                                ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │                 load_context_node                        │
                       │     (加载健康数据、用药记录、对话历史、短期记忆)            │
                       └─────────────────────────────────────────────────────────┘
                                                │
                                                ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │                   classify_intent                        │
                       │         (LLM 意图分类: health/med/insight/general)       │
                       └─────────────────────────────────────────────────────────┘
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    │                           │                           │
                    ▼                           ▼                           ▼
        ┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐
        │  health_advisor   │     │ medication_agent  │     │  insight_analyst  │
        │   (ReAct Loop)    │     │   (ReAct Loop)    │     │   (ReAct Loop)    │
        │                   │     │                   │     │                   │
        │ Thought → Action  │     │ Thought → Action  │     │ Thought → Action  │
        │     → Observe     │     │     → Observe     │     │     → Observe     │
        │   (max 3 iters)   │     │   (max 3 iters)   │     │   (max 3 iters)   │
        └───────────────────┘     └───────────────────┘     └───────────────────┘
                    │                           │                           │
                    └───────────────────────────┼───────────────────────────┘
                                                │
                                                ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │                   reflection_node                        │
                       │     (质量评分: 完整性/安全/语气/准确性/个性化)             │
                       │                  ≥8/10 PASS, <8 RETRY                   │
                       └─────────────────────────────────────────────────────────┘
                                                │
                           ┌────────────────────┴────────────────────┐
                           │                                         │
                      score ≥ 8                                 score < 8
                           │                                         │
                           ▼                                         ▼
                       ┌───────────┐                         ┌───────────────────┐
                       │synthesize │                         │ retry 对应 Agent   │
                       │  (END)    │                         │    (max 2 次)     │
                       └───────────┘                         └───────────────────┘
                                                                     │
                                                                     └──→ 返回对应子 Agent (health_advisor/medication_agent/insight_analyst)
```

### ReAct 模式（Reason + Act）

每个子 Agent 都采用 ReAct 模式进行推理：

```
Thought: 分析用户问题，决定需要什么信息
Action: query_health_data
Action Input: {"data_type": "blood_pressure", "days": 7}
Observation: 收到工具返回的数据
Thought: 数据显示血压偏高，需要查阅相关建议
Action: None  (直接生成回答)
Final Answer: 您最近7天的血压数据显示略有波动...
```

**ReAct 优势**：
- ✅ 工具调用更精准（先思考再行动）
- ✅ 推理过程可追溯（便于调试）
- ✅ 减少幻觉（基于真实数据回答）

### Reflection 质量守护

Reflection 节点在子 Agent 输出后进行质量评估，评分维度：

| 维度 | 说明 | 分值 |
|------|------|------|
| **完整性** | 是否完整回答了用户问题 | 0-2 |
| **安全边界** | 是否避免了诊断/改药建议 | 0-2 |
| **语气** | 是否温和、不引起恐慌 | 0-2 |
| **准确性** | 是否基于数据、无杜撰 | 0-2 |
| **个性化** | 是否使用了用户实际数据 | 0-2 |

- **总分 ≥ 8/10**：通过，进入合成输出
- **总分 < 8**：重试（最多 2 次），附带改进指导

### 子 Agent 工具清单

| Agent | 工具 | 说明 |
|-------|------|------|
| **Health Advisor** | `query_health_data` | 查询健康数据（血压/血糖/体重等） |
|  | `calculate_bmi` | 计算 BMI 指数 |
|  | `get_weather` | 获取天气信息 |
|  | `calculate_water_intake` | 计算建议饮水量 |
| **Medication Agent** | `search_medication_info` | 查询药品信息 |
|  | `check_drug_interaction` | 检查药物相互作用 |
|  | `query_medication_records` | 查询用药记录 |
| **Insight Analyst** | `analyze_health_trend` | 分析健康趋势 |
|  | `generate_weekly_summary` | 生成周报摘要 |
|  | `compare_periods` | 对比两个时间段数据 |

### 子 Agent 职责

| Agent | 职责 | RAG Collection |
|-------|------|----------------|
| Health Advisor | 日报建议、自适应追问、健康 Q&A | health, tcm |
| Medication Agent | 用药 NLP 解析、药品查询、用药信息整理 | medication |
| Insight Analyst | 周/月趋势分析、异常识别、数据洞察 | health, tcm |

## 认知记忆系统（规划中）

> 参考人类认知心理学设计，借鉴 HelloAgents 四种记忆类型架构

### 记忆类型映射

| 记忆类型 | 人类对应 | HEI 应用场景 | 存储后端 | 特点 |
|----------|---------|-------------|----------|------|
| **Working** | 工作记忆 | 当前对话上下文 | Redis | TTL 60min, 容量 50 条 |
| **Episodic** | 情景记忆 | 健康事件时间轴（量血压、吃药、运动、就医） | PostgreSQL | 时间戳 + 事件标签 |
| **Semantic** | 语义记忆 | 用户健康画像（慢性病、过敏、用药禁忌） | PostgreSQL + pgvector | 概念 + 领域分类 |
| **Perceptual** | 感知记忆 | 处理过的体检报告、健康文档 | PostgreSQL | 文件哈希去重 |

### 架构图

```
┌────────────────────────────────────────────────────────────────────┐
│                   HEI-agent Cognitive Memory System                │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────┐│
│  │   Working    │  │   Episodic   │  │   Semantic   │  │Perceptual│
│  │   Memory     │  │   Memory     │  │   Memory     │  │ Memory  ││
│  ├──────────────┤  ├──────────────┤  ├──────────────┤  ├─────────┤│
│  │ 当前对话     │  │ 健康事件时间轴 │  │ 用户健康画像 │  │体检报告 ││
│  │ TTL: 60min  │  │ 量血压/吃药   │  │ 慢性病/过敏  │  │处理记录 ││
│  │ 容量: 50条  │  │ 运动/就医     │  │ 用药禁忌     │  │哈希去重 ││
│  │             │  │ 带时间戳      │  │ 向量检索     │  │         ││
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────┘│
│         │                 │                 │               │     │
│         └────────────┬────┴─────────────────┴───────────────┘     │
│                      ▼                                            │
│              ┌──────────────────┐                                 │
│              │ CognitiveMemory  │  ← 统一接口                     │
│              │ Manager          │                                 │
│              │ add/search/      │                                 │
│              │ consolidate/     │                                 │
│              │ forget           │                                 │
│              └──────────────────┘                                 │
└────────────────────────────────────────────────────────────────────┘
```

### LangGraph 集成流程

```
START → load_context → classify_intent → sub-agent(ReAct) → reflection → synthesize
                                                                            │
                                                                            ▼
                                                              ┌─────────────────────────┐
                                                              │ memory_consolidation    │
                                                              │ (新增节点)               │
                                                              ├─────────────────────────┤
                                                              │ 1. 存入 working memory  │
                                                              │ 2. 提取健康事件→episodic │
                                                              │ 3. 更新健康画像→semantic │
                                                              │ 4. 重要性≥0.7 自动整合  │
                                                              └─────────────────────────┘
                                                                            │
                                                                            ▼
                                                                          END
```

### 核心操作

| 操作 | 说明 | 触发时机 |
|------|------|---------|
| `add` | 存入记忆 | 每轮对话后 |
| `search` | 检索相关记忆 | load_context 阶段 |
| `consolidate` | 将 working 中重要内容升级到 episodic/semantic | synthesize 之后 |
| `forget` | 清除低重要性记忆 | 定时任务 / 容量满时 |

### 数据结构

```python
# 记忆条目结构
MemoryRecord = {
    "id": str,              # UUID 前 8 位
    "user_id": UUID,        # 用户 ID
    "memory_type": str,     # working / episodic / semantic / perceptual
    "content": str,         # 记忆内容
    "importance": float,    # 重要性评分 0.0 ~ 1.0
    "created_at": float,    # Unix 时间戳
    "metadata": {           # 扩展字段
        # episodic 专用
        "event_type": str,       # blood_pressure / medication / exercise / visit
        "location": str,         # 地点

        # semantic 专用
        "concept": str,          # 概念标签（如 "hypertension", "allergy"）
        "domain": str,           # 领域（chronic_disease / preference / contraindication）

        # perceptual 专用
        "file_hash": str,        # 文件哈希（去重用）
        "modality": str,         # document / image
    }
}
```

### 健康场景示例

```python
# 1. 用户量血压后对话
memory.add({
    "content": "用户今早测量血压 145/92 mmHg，略高于正常范围",
    "memory_type": "episodic",
    "importance": 0.8,
    "event_type": "blood_pressure",
    "timestamp": "2026-03-05T08:30:00"
})

# 2. 识别到用户有高血压，更新健康画像
memory.add({
    "content": "用户有高血压病史，需关注血压波动",
    "memory_type": "semantic",
    "importance": 0.95,
    "concept": "hypertension",
    "domain": "chronic_disease"
})

# 3. 下次对话时检索相关记忆
relevant = memory.search({
    "query": "血压",
    "memory_type": "episodic",
    "limit": 5
})
# → 返回最近的血压测量记录，供 Agent 参考
```

### 实现计划

| 阶段 | 任务 | 文件 |
|------|------|------|
| Phase 1 | 创建 `CognitiveMemoryTool` 类，统一四种记忆操作 | `app/memory/cognitive_memory.py` |
| Phase 2 | 更新 `AgentState`，添加记忆相关字段 | `app/agents/state.py` |
| Phase 3 | 添加 `memory_consolidation_node` 到 LangGraph | `app/agents/orchestrator.py` |
| Phase 4 | 在 `load_context_node` 中集成记忆检索 | `app/agents/orchestrator.py` |
| Phase 5 | 数据库迁移，添加记忆表 | `alembic/versions/` |

## LLM Router

支持多 Provider 自动 failover：

1. **DeepSeek** — 优先使用（与 Android 端一致）
2. **GLM (智谱)** — 备选（免费额度）
3. **OpenAI** — 最后备选

配置 `.env` 中的 API key 即可启用对应 Provider。未配置 key 的 Provider 自动跳过。
连续失败 3 次的 Provider 自动冷却 5 分钟后重试。

## 知识库管理

将文档放入 `data/knowledge/` 对应子目录，运行导入脚本：

```bash
# 导入全部
python scripts/ingest_knowledge.py

# 导入指定 collection
python scripts/ingest_knowledge.py --collection health
```

支持格式：txt, md, pdf

## 部署到 Ubuntu 24 服务器

```bash
# 1. 安装 Docker
curl -fsSL https://get.docker.com | sh

# 2. 克隆项目并配置
git clone <repo> && cd hel-agent
cp .env.example .env
vim .env  # 填入 API keys 和生产配置

# 3. 启动
docker-compose up -d

# 4. 初始化数据库
docker exec hel-agent python scripts/init_db.py

# 5. 导入知识库
docker exec hel-agent python scripts/ingest_knowledge.py
```

## 项目结构

```
hel-agent/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py             # 配置管理
│   ├── database.py           # SQLAlchemy 异步引擎
│   ├── auth/                 # JWT 认证
│   ├── api/v1/               # REST API 路由
│   │   ├── chat.py           # Agent 对话
│   │   ├── health.py         # 健康数据 API
│   │   ├── medication.py     # 用药 API
│   │   └── sync.py           # 数据同步
│   ├── agents/               # LangGraph 多 Agent
│   │   ├── orchestrator.py   # 编排器（Supervisor）
│   │   ├── health_advisor.py # 健康顾问 (ReAct)
│   │   ├── medication_agent.py # 用药管家 (ReAct)
│   │   ├── insight_analyst.py  # 洞察分析 (ReAct)
│   │   ├── reflection.py     # Reflection 质量守护节点
│   │   ├── tools.py          # 工具定义 (LangChain @tool)
│   │   └── state.py          # 共享状态定义 (TypedDict)
│   ├── llm/router.py         # LLM Router (LiteLLM)
│   ├── rag/                  # RAG 引擎 (Qdrant)
│   ├── memory/               # 记忆系统 (Redis + PostgreSQL)
│   ├── mcp/                  # MCP 工具服务
│   ├── models/               # SQLAlchemy ORM
│   └── schemas/              # Pydantic 请求/响应
├── data/knowledge/           # RAG 知识库文档
├── scripts/                  # 工具脚本
├── tests/                    # 测试
├── alembic/                  # 数据库迁移
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## License

Private — for HElDairy project use only.
