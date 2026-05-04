# HEl Agent — AI 健康管家后端

> HElDairy 的 Agent 智能后端系统，基于 LangGraph 构建
> 
> **v2 重构**: Pipeline 模式 + 可插拔架构（2026-05-03）
>
## 演示
<img width="1014" height="1508" alt="QQ_1777889368245" src="https://github.com/user-attachments/assets/9ea79459-5eeb-47df-9228-a974d362a134" />


## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                     HElDairy Android App                        │
│  (Retrofit → Agent API, JWT auth, 数据同步)                      │
└─────────────────┬───────────────────────────────────────────────┘
                  │ HTTPS / REST
┌─────────────────▼───────────────────────────────────────────────┐
│                   FastAPI Gateway (hel-agent)                    │
│  /auth/* │ /api/v1/chat │ /api/v1/health/* │ /api/v1/med/*     │
├─────────────────────────────────────────────────────────────────┤
│                    Pipeline Architecture (v2)                    │
│  ┌──────────────────┐    ┌──────────────────────────────────┐   │
│  │  FastPipeline     │    │  AgentPipeline (LangGraph)       │   │
│  │  (单次LLM调用)    │    │  Router→ReAct→Reflection→Save    │   │
│  └──────────────────┘    └──────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                   ContextAssembler                               │
│  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐ ┌─────────┐ │
│  │Health   │ │Medication│ │Memory  │ │RAG       │ │Conv     │ │
│  │Provider │ │Provider  │ │Provider│ │Provider  │ │History  │ │
│  └─────────┘ └──────────┘ └────────┘ └──────────┘ └─────────┘ │
├─────────────────────────────────────────────────────────────────┤
│              Shared Infrastructure Layer                         │
│  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌────────────────────┐   │
│  │LLM Router│ │RAG Engine│ │Memory  │ │User Data Store     │   │
│  │(LiteLLM) │ │(Qdrant)  │ │Manager │ │(PostgreSQL)        │   │
│  └─────────┘ └──────────┘ └────────┘ └────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 技术栈

### 核心组件

| 层级 | 技术 | 版本/型号 | 说明 |
|------|------|----------|------|
| Agent 框架 | LangGraph | ≥ 0.2.40 | 有状态图、条件路由、checkpointer、ReAct 循环 |
| Pipeline 模式 | 自研 | v2 | FastPipeline + AgentPipeline，解耦编排逻辑 |
| LLM Router | LiteLLM | - | 多 Provider 统一接口、自动 failover |
| 向量数据库 | Qdrant | ≥ 1.7 | 3 个 Collection、Cosine 相似度 |
| 关系数据库 | PostgreSQL | 16 + pgvector | 用户数据、长期记忆、向量检索 |
| 缓存 | Redis | 7 | 短期会话记忆、TTL 自动过期 |
| API 框架 | FastAPI | ≥ 0.109 | 异步、自动 OpenAPI、Pydantic v2 |
| 认证 | JWT (PyJWT) | - | HS256 算法、Access + Refresh Token |
| 工具协议 | MCP | v1 | Model Context Protocol 标准化工具调用 |

### LLM 模型配置

| Provider | 模型 | 用途 | 
|----------|------|------|
| **DeepSeek** | `deepseek-chat` | 
| **智谱 GLM** | `glm-4.7` | 
| **OpenAI** | `gpt-4o-mini` | 

**Failover 策略**：连续失败 3 次 → 冷却 5 分钟 → 自动重试

### Embedding 配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| Provider | 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` |
| Model | `embedding-3` | 智谱最新 Embedding 模型 |
| 维度 | **2048** | 向量维度 |
| 调用方式 | LiteLLM `aembedding()` | 统一异步接口 |

### RAG 配置

| 参数 | 值 | 说明 |
|------|-----|------|
| `chunk_size` | 800 | 文档分块大小（字符） |
| `chunk_overlap` | 200 | 分块重叠（保证上下文连续） |
| `rerank_top_k` | 20 | 初筛候选数量 |
| `top_k` | 5 | 最终返回结果数 |
| 相似度算法 | Cosine Distance | `models.Distance.COSINE` |

### Memory 配置

| 记忆类型 | 存储 | 配置 |
|----------|------|------|
| 短期记忆 | Redis | TTL = 24h, max_turns = 20 |
| 长期记忆 | PostgreSQL + pgvector | decay_rate = 0.95, 带向量 |
| 语义记忆 | Qdrant `user_semantic` | 用户健康画像、偏好（规划中） |

## 项目结构（v2 重构后）

```
HEI-agent/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── config.py                  # Pydantic Settings 配置
│   ├── database.py                # SQLAlchemy 异步引擎
│   │
│   ├── pipelines/                 # ⭐ Pipeline 层（v2 新增）
│   │   ├── __init__.py            # 导出 AgentContext, Pipeline, FastPipeline, AgentPipeline
│   │   ├── base.py                # Pipeline 抽象基类 + AgentContext 共享上下文
│   │   ├── fast_pipeline.py       # 快速路径：单次 LLM 调用
│   │   └── agent_pipeline.py      # 完整路径：LangGraph 编排
│   │
│   ├── agents/                    # Agent 层
│   │   ├── base.py                # ⭐ Agent 基类（统一工具注册、记忆注入）
│   │   ├── router.py              # ⭐ IntentRouter（意图分类，从 orchestrator 解耦）
│   │   ├── orchestrator.py        # 兼容性包装器（导入新模块，保持旧 API）
│   │   ├── state.py               # 共享 AgentState
│   │   ├── health_advisor.py      # 健康顾问 Agent (ReAct)
│   │   ├── medication_agent.py    # 用药管家 Agent (ReAct)
│   │   ├── insight_analyst.py     # 洞察分析师 Agent (ReAct)
│   │   ├── reflection.py          # 质量审核/反思节点
│   │   └── tools.py               # Agent 工具定义
│   │
│   ├── context/                   # ⭐ 上下文组装层（v2 新增）
│   │   ├── __init__.py
│   │   ├── assembler.py           # ContextAssembler（并行加载所有数据源）
│   │   └── providers/             # 各数据源独立 Provider
│   │       ├── health_data.py     # 健康数据 Provider
│   │       ├── medication_data.py # 用药数据 Provider
│   │       ├── memory_provider.py # 长期记忆 Provider
│   │       └── rag_provider.py    # RAG 检索 Provider
│   │
│   ├── llm/
│   │   └── router.py              # 多 LLM 提供商路由 + 自动 failover
│   ├── rag/
│   │   ├── engine.py              # 混合检索引擎 (Qdrant + ES + Rerank)
│   │   └── ingest.py              # 知识入库
│   ├── memory/
│   │   ├── manager.py             # 记忆管理器
│   │   ├── short_term.py          # Redis 短期记忆
│   │   └── long_term.py           # PostgreSQL + pgvector 长期记忆
│   ├── mcp/                       # MCP 工具服务
│   ├── api/v1/
│   │   ├── chat.py                # 聊天 API（使用 FastPipeline + ContextAssembler）
│   │   ├── health.py              # 健康 API
│   │   ├── medication.py          # 用药 API
│   │   └── sync.py                # 数据同步 API
│   ├── auth/                      # JWT 认证
│   ├── models/                    # SQLAlchemy ORM 模型
│   └── schemas/                   # Pydantic 请求/响应模型
├── scripts/                       # 工具脚本
├── data/knowledge/                # 知识库目录
├── alembic/                       # 数据库迁移
├── tests/                         # 测试
└── Dockerfile
```

## 快速开始

### 1. 环境准备

```bash
cp .env.example .env
# 编辑 .env，填入至少一个 LLM provider 的 API key
```

### 2. Docker 启动

```bash
docker compose up -d
```

这会启动 4 个服务：
- `hel-agent` — FastAPI 应用 (端口 8011)
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

# 启动服务（推荐：单进程，避免 --reload 子进程残留）
scripts/dev_server.sh start

# 查看状态 / 日志 / 停止
scripts/dev_server.sh status
scripts/dev_server.sh logs
scripts/dev_server.sh stop
```

### 4. 验证

```bash
# 健康检查
curl http://localhost:8011/health

# 注册用户
curl -X POST http://localhost:8011/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","email":"demo@test.com","password":"Demo123456"}'

# 登录获取 token
curl -X POST http://localhost:8011/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"Demo123456"}'

# 使用 token 对话
curl -X POST http://localhost:8011/api/v1/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"我最近睡眠不太好，有什么建议吗？"}'
```

## 🎮 Demo 模式（演示版前后端）

Demo 模式是一个**开箱即用**的演示方案，无需 PostgreSQL、Redis、JWT 认证，仅需 Qdrant + LLM API key 即可运行完整的前后端。

### 功能概览

| 功能 | 说明 |
|------|------|
| 💬 **AI 对话** | 基于 DeepSeek + RAG 知识库的智能健康问答 |
| 📚 **RAG 检索** | 3 个知识库（健康 / 用药 / 中医），774 条知识 |
| 📋 **会话管理** | 创建、切换、重命名、删除会话，消息自动保存 |
| 📊 **健康日报** | 12 道问题 → AI 分析 → 个性化建议 |
| 📈 **健康洞察** | 睡眠 / 运动 / 情绪趋势图（演示数据） |
| 💊 **用药管理** | 药物添加、编辑、删除、启用/停用 |

### 快速启动

```bash
# === 1. 启动后端（demo 模式）===
cd /home/admin/workspace/HEI-agent

# 确保 .env 中已配置：
#   DEMO_MODE=true
#   DEEPSEEK_API_KEY=sk-xxx
#   DASHSCOPE_API_KEY=sk-xxx   （阿里云百炼，用于 embedding）
#   QDRANT_URL=http://localhost:6333

# 启动后端服务（端口 8000）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# === 2. 启动前端 ===
cd demo-frontend

# 安装依赖（首次）
npm install

# 启动开发服务器（端口 5173）
npm run dev -- --host 0.0.0.0 --port 5173
```

### Demo 模式存档（minimal 环境）

在内存受限（~2GB）的服务器上运行只需：

| 服务 | 进程 | 内存 | 端口 | 命令 |
|------|------|------|------|------|
| Qdrant | Docker 容器 | ~100MB | 6333 | `docker run -d -p 6333:6333 qdrant/qdrant` |
| 后端 | Python uvicorn | ~330MB | 8000 | `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| 前端 | Vite dev server | ~80MB | 5173 | `cd demo-frontend && npm run dev -- --host 0.0.0.0 --port 5173` |

**总计约 510MB**，无需 PostgreSQL 和 Redis。

### 知识库导入

```bash
# 导入知识库（仅需执行一次，Qdrant 已运行时）
python scripts/ingest_knowledge.py --demo

# 验证导入结果
curl -s http://localhost:6333/collections | python3 -c "
import sys,json
for name, info in json.load(sys.stdin)['result']['collections'].items():
    print(f'{name}: {info[\"points_count\"]} chunks')
"
# 预期输出：
# health_knowledge: 68 chunks
# medication_info: 37 chunks
# tcm_wellness: 669 chunks
```

### 访问地址

| 地址 | 说明 |
|------|------|
| `http://localhost:5173` | 🎨 前端页面 |
| `http://localhost:8000/health` | 🏥 后端健康检查 |
| `http://localhost:8000/docs` | 📖 API 文档（Swagger UI） |

### 测试示例

```bash
# 通过前端代理发送对话（Vite 自动转发 /api → 后端 8000）
curl -X POST http://localhost:5173/api/demo/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"高血压患者饮食需要注意什么？","session_id":"test-001"}'

# 会话管理
curl -X POST http://localhost:5173/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"title":"高血压饮食咨询"}'

curl http://localhost:5173/api/v1/sessions
```

### 前后端代理架构

```
浏览器 (localhost:5173)
    │
    ▼
Vite Dev Server (端口 5173)
    │  /api/* → proxy → localhost:8000
    ▼
FastAPI Backend (端口 8000, DEMO_MODE=true)
    │  /api/demo/chat     → 对话接口
    │  /api/v1/sessions   → 会话 CRUD
    │  /health            → 健康检查
    │
    ▼
Qdrant (端口 6333)  ← RAG 向量检索
DeepSeek API         ← 对话生成
DashScope API        ← Embedding (text-embedding-v4, dim=1024)
```

---

## Pipeline 架构（v2 核心重构）

### 设计理念

将原来的 `orchestrator.py`（500+ 行，承载所有逻辑）拆分为清晰的 **Pipeline 模式**：

```
Before (耦合):
orchestrator.py → 意图分类 + 快速路径 + 完整路径 + 存储 + 反思

After (分层):
Pipeline (抽象基类)
├── FastPipeline      → 单次 LLM 调用，3-15s 响应
└── AgentPipeline     → LangGraph 全编排，ReAct + Reflection
```

### 核心组件

#### 1. AgentContext — 共享上下文

```python
@dataclass
class AgentContext:
    """Pipeline 执行时的共享上下文"""
    user_id: str
    session_id: str
    user_message: str
    
    # 由 ContextAssembler 并行加载
    health_context: str = ""
    medication_context: str = ""
    conversation_history: str = ""
    long_term_memories: list[str] = field(default_factory=list)
    knowledge_context: str = ""
    
    # Agent 间运行时共享状态
    intermediate_results: dict = field(default_factory=dict)
    
    async def load(self, assembler: ContextAssembler) -> None:
        """并行加载所有数据源"""
        data = await assembler.load_all(...)
        # ... 填充各字段
```

#### 2. ContextAssembler — 并行上下文加载

```python
class ContextAssembler:
    """替代 chat.py 和 orchestrator.py 中散落的加载逻辑"""
    
    async def load_all(self, user_id, session_id, message) -> dict:
        """并行加载 5 个数据源"""
        health_ctx, med_ctx, memories, knowledge_ctx, history = await asyncio.gather(
            fetch_health_context(...),
            fetch_medication_context(...),
            fetch_long_term_memories(...),
            fetch_rag_context(...),
            fetch_conversation_history(...),
        )
        return { ... }
```

#### 3. FastPipeline — 快速路径

```python
class FastPipeline(Pipeline):
    """单次 LLM 调用，无分类/ReAct/Reflection"""
    
    async def execute(self, ctx: AgentContext) -> dict:
        context = await self.assembler.assemble(ctx)  # 统一组装
        response = await self.llm.chat(context)
        return {"response": response, "agent_used": "kitty_chat"}
```

#### 4. AgentPipeline — 完整路径

```python
class AgentPipeline(Pipeline):
    """LangGraph 全编排"""
    
    async def execute(self, ctx: AgentContext) -> dict:
        graph = get_compiled_graph()  # LangGraph StateGraph
        result = await graph.ainvoke(initial_state)
        return { ... }
```

#### 5. IntentRouter — 意图分类

```python
class IntentRouter:
    """从 orchestrator.py 解耦的意图分类器"""
    
    async def classify_intent(self, user_message: str) -> str:
        # LLM 分类: health / medication / insight / general
        ...
```

#### 6. BaseAgent — Agent 基类

```python
class BaseAgent(ABC):
    """统一的 Agent 基类"""
    
    @abstractmethod
    def _register_tools(self) -> None: ...
    
    @abstractmethod
    async def react(self, state: AgentState) -> dict: ...
```

### 向后兼容

`orchestrator.py` 保留为**兼容性包装器**，原始 API 签名不变：

```python
# 旧代码仍然可用
from app.agents.orchestrator import run_chat, run_agent

# 新代码推荐使用
from app.pipelines import FastPipeline, AgentPipeline, AgentContext
from app.context.assembler import ContextAssembler
```

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
                       │         (IntentRouter: health/med/insight/general)       │
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
                                                                     └──→ 返回对应子 Agent
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
| **Working** | 工作记忆 | 当前对话上下文 | **Redis** | TTL 60min, 容量 50 条 |
| **Episodic** | 情景记忆 | 健康事件时间轴（量血压、吃药、运动、就医） | **PostgreSQL** | 时间戳 + 事件标签，支持时间范围查询 |
| **Semantic** | 语义记忆 | 用户健康画像（慢性病、过敏、用药禁忌） | **Qdrant** | 向量检索，复用 RAG 引擎 |
| **Perceptual** | 感知记忆 | 处理过的体检报告、健康文档 | **PostgreSQL** | 文件哈希去重 |

## LLM Router

支持多 Provider 自动 failover：

1. **DeepSeek** — 优先使用（与 Android 端一致）
2. **GLM (智谱)** — 备选（免费额度）
3. **OpenAI** — 最后备选

配置 `.env` 中的 API key 即可启用对应 Provider。未配置 key 的 Provider 自动跳过。
连续失败 3 次的 Provider 自动冷却 5 分钟后重试。

## RAG 检索增强生成系统

RAG（Retrieval-Augmented Generation）让 Agent 能够基于专业知识库回答问题，而非仅靠 LLM 内置知识。

### 架构流程

```
用户问题
   │
   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         RAG Engine                                    │
├──────────────────────────────────────────────────────────────────────┤
│  ① Embedding                                                         │
│     用户问题 ─→ LLM Router ─→ 向量 (2048维)                           │
├──────────────────────────────────────────────────────────────────────┤
│  ② Multi-Collection Search                                           │
│     ┌─────────────────┬─────────────────┬─────────────────┐          │
│     │ health_knowledge│ medication_info │   tcm_wellness  │          │
│     │   (健康知识)    │   (药品信息)    │   (中医养生)    │          │
│     └────────┬────────┴────────┬────────┴────────┬────────┘          │
│              │                 │                 │                   │
│              └─────────────────┼─────────────────┘                   │
│                                ▼                                      │
│                    Qdrant Vector Search                               │
│                    (Cosine Similarity)                                │
├──────────────────────────────────────────────────────────────────────┤
│  ③ RRF Fusion + Rerank                                               │
│     Dense (向量) + Sparse (BM25) → RRF 融合 → 智谱 Rerank 精排        │
├──────────────────────────────────────────────────────────────────────┤
│  ④ Context Injection                                                 │
│     Top-K 结果 → 注入 Agent System Prompt                            │
└──────────────────────────────────────────────────────────────────────┘
```

## API 文档

启动后访问 http://localhost:8011/docs 查看自动生成的 Swagger UI。

### 核心端点

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/auth/register` | 用户注册 |
| POST | `/auth/login` | 登录获取 JWT |
| POST | `/auth/refresh` | 刷新 token |
| GET  | `/auth/me` | 当前用户信息 |
| POST | `/api/v1/chat` | 统一 Agent 对话 |
| POST | `/api/v1/chat/stream` | SSE 流式对话 |
| POST | `/api/v1/health/daily-advice` | 日报建议（Android 兼容） |
| POST | `/api/v1/health/follow-up` | 自适应追问（Android 兼容） |
| POST | `/api/v1/health/weekly-insight` | 周洞察（Android 兼容） |
| POST | `/api/v1/medication/parse-nlp` | 用药 NLP 解析（Android 兼容） |
| POST | `/api/v1/medication/info-summary` | 药品信息摘要 |
| POST | `/api/v1/sync/upload` | 数据同步上传 |
| GET  | `/api/v1/sync/status` | 同步状态查询 |
| GET  | `/health` | 系统健康检查 |
