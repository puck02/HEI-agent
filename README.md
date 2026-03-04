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

### Orchestrator（编排器）

```
START → load_context → classify_intent ─┬─ health  → health_advisor  → synthesize → END
                                         ├─ med     → medication_agent → synthesize → END
                                         ├─ insight → insight_analyst  → synthesize → END
                                         └─ general → direct_answer    → synthesize → END
```

### 子 Agent 职责

| Agent | 职责 | RAG Collection |
|-------|------|----------------|
| Health Advisor | 日报建议、自适应追问、健康 Q&A | health, tcm |
| Medication Agent | 用药 NLP 解析、药品查询、用药信息整理 | medication |
| Insight Analyst | 周/月趋势分析、异常识别、数据洞察 | health, tcm |

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
│   │   ├── health_advisor.py # 健康顾问
│   │   ├── medication_agent.py # 用药管家
│   │   ├── insight_analyst.py  # 洞察分析
│   │   └── state.py          # 共享状态定义
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
