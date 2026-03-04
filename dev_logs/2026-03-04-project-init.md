# 2026-03-04 — hel-agent 项目初始化

## 概述

创建了 hel-agent 项目——HElDairy 的 AI 健康管家多 Agent 后端系统。

## 完成内容

### Phase 0: 项目脚手架
- 创建完整项目目录结构
- Docker Compose 配置（PostgreSQL 16 + pgvector、Redis 7、Qdrant、FastAPI）
- Dockerfile（Python 3.11-slim）
- requirements.txt（锁定核心依赖版本）
- .env.example（全量配置模板）

### Phase 1: 基础设施
- **Config** — Pydantic Settings，从 .env 加载所有配置
- **Database** — SQLAlchemy 2.0 异步引擎 + sessionmaker
- **User 模型** — UUID 主键，username/email 唯一索引
- **JWT 认证** — 完整注册/登录/刷新/me 流程，bcrypt 密码哈希

### Phase 2: LLM Router
- **LiteLLM 封装** — 统一 DeepSeek/GLM/OpenAI 调用接口
- **自动 failover** — 按优先级尝试，连续失败 3 次冷却 5 分钟
- **Embedding 支持** — 统一嵌入接口，可切换 Provider

### Phase 3: 数据模型
- **Health 模型** — HealthEntry、QuestionResponse、DailyAdvice、DailySummary、InsightReport、AdviceTracking（完整映射 Android Room 实体）
- **Medication 模型** — Medication、MedicationCourse、MedicationEvent、MedicationReminder
- **Memory 模型** — MemoryEntry（支持 embedding 存储）

### Phase 4: 记忆系统
- **ShortTermMemory** — Redis 会话记忆，滑动窗口 20 轮，TTL 24h
- **LongTermMemory** — PostgreSQL 持久记忆，cosine 相似度检索，importance 衰减
- **MemoryManager** — 编排短期+长期记忆，支持对话洞察提取

### Phase 5: RAG 引擎
- **Qdrant 向量检索** — 3 个 Collection（health、medication、tcm）
- **文档导入管线** — 支持 txt/md/pdf，RecursiveCharacterTextSplitter
- **跨 collection 检索** — 多知识库联合搜索 + 元数据过滤

### Phase 6: MCP 工具系统
- **MCP Server** — 基于 mcp SDK，SSE 传输
- **4 个工具** — calculator、weather（wttr.in）、web_search（DuckDuckGo）、health_data_query
- Calculator 安全沙箱（whitelist eval）

### Phase 7: Multi-Agent 系统（LangGraph）
- **Orchestrator** — LangGraph StateGraph，意图分类 → 条件路由
- **Health Advisor** — 日报建议、自适应追问、健康 Q&A
- **Medication Agent** — NLP 用药解析、药品信息摘要
- **Insight Analyst** — 周洞察生成、趋势分析
- 所有输出 JSON schema 与 Android 端 100% 兼容

### Phase 8: API 集成层
- **Chat API** — 统一对话入口 `/api/v1/chat`
- **Health API** — daily-advice、follow-up、weekly-insight（Android 兼容）
- **Medication API** — parse-nlp、info-summary（Android 兼容）
- **Sync API** — 增量数据同步（客户端优先冲突解决）

## Android 端变更影响

后续需要在 HElDairy Android 端：
1. 新增 `AgentApiService.kt` + `AgentClient.kt`（Retrofit，JWT 认证）
2. 新增 `DataSyncManager.kt`（WorkManager 定期同步）
3. 修改 Coordinator 层增加 Agent 调用路径（Feature Flag 控制）
4. 设置页增加 Agent 配置（服务器地址、登录、同步开关）

## 技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| LLM 路由 | LiteLLM | 100+ Provider、内置 fallback/retry |
| 向量库 | Qdrant | 生产级、多租户、元数据过滤 |
| 长期记忆 | PostgreSQL + ARRAY(Float) | 与用户数据同库，减少运维 |
| RAG 知识库 | Qdrant | 专业向量检索 |
| 工具协议 | MCP | 标准化、可复用 |
| 保留直连 | DeepSeek fallback | Agent 不可用时 App 仍正常工作 |

## 下一步

- [ ] Ubuntu 24 服务器部署验证
- [ ] 知识库文档收集与导入
- [ ] Android 端 Agent Integration 分支开发
- [ ] E2E 测试覆盖

---

## 验证记录

### Import 验证（全量 30 个模块通过）

1. **修复 `app/schemas/health.py` 前向引用**：将 `HealthEntrySync`, `MedicationSync`, `MedicationCourseSync` 等叶子类型移到 `SyncUploadRequest` 之前定义，解决 Pydantic v2 前向引用问题。
2. **补充 `requirements.txt`**：
   - 新增 `langchain-text-splitters>=0.3.0`（显式声明，防止版本漂移）
   - 新增 `email-validator>=2.2.0`（Pydantic EmailStr 依赖）
3. **创建 `tests/__init__.py`** 和 `alembic/versions/.gitkeep`
4. **本地 venv 验证**：30/30 模块 import 通过（schemas、config、agents、auth、llm、memory、rag、mcp、models、api routes、main）
