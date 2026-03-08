# 2026-03-08 Android-Backend 对接实施记录（Phase 1）

## 目标
- 启动“HEl Android ↔ HEI-agent Backend”对接实施。
- 优先完成第一批高价值改造：
  1) 修复本机 Docker 运行环境阻塞
  2) 修正后端 `auth/register` 契约（返回 token）
  3) 修正 medication schema 默认值问题
  4) 增补基础契约测试并执行

## 已完成改动

### 1) Docker 环境修复（本机层）
- 问题：`docker-compose` 报错缺少 `buildx` 和 `docker-credential-desktop`。
- 处理：
  - 安装 `docker-buildx`、`docker-credential-helper`
  - 调整 `~/.docker/config.json`：
    - `credsStore` 从 `desktop` 改为 `osxkeychain`
    - 增加 `cliPluginsExtraDirs` 指向 `/opt/homebrew/lib/docker/cli-plugins`
- 结果：`docker buildx version` 和 `docker compose version` 均可用。

### 2) 后端 Auth 契约修复
- 文件：`app/auth/router.py`
- 变更：
  - `/auth/register` 的 `response_model` 从 `UserResponse` 改为 `TokenResponse`
  - 注册成功后直接生成并返回 `access_token` / `refresh_token` / `expires_in`
- 目的：与 Android 侧 `AgentApi.register()` 当前期望（token 返回）一致。

### 3) Medication schema 安全修复
- 文件：`app/schemas/medication.py`
- 变更：
  - 将多个 list 默认值从 `[]` 改为 `Field(default_factory=list)`
- 目的：避免可变默认值共享导致的数据污染风险。

### 4) Pydantic 配置升级
- 文件：`app/auth/schemas.py`
- 变更：
  - `UserResponse` 从 `class Config` 改为 `model_config = ConfigDict(from_attributes=True)`
- 目的：消除 Pydantic v2 deprecation 警告。

### 5) Compose 文件清理
- 文件：`docker-compose.yml`
- 变更：
  - 移除过时 `version: "3.9"`
- 目的：消除新版本 Compose warning。

## 新增测试
- `tests/test_auth_register_contract.py`
  - 校验注册请求必须包含 email
- `tests/test_auth_router_contract.py`
  - 校验 `/auth/register` 的响应模型为 `TokenResponse`
- `tests/test_medication_schema_defaults.py`
  - 校验 medication schema 的 list 默认值互不污染

## 测试执行记录

### Pytest（临时 venv）
- 命令：
  - `PYTHONPATH=. /tmp/hei-agent-venv/bin/python -m pytest -q tests/test_auth_register_contract.py tests/test_medication_schema_defaults.py tests/test_auth_router_contract.py`
- 结果：`4 passed`

### 依赖容器（docker run）
- 启动：`hel-postgres`, `hel-redis`, `hel-qdrant`
- 状态：均为 `Up`

### API Smoke（uvicorn + curl）
- `GET /health` => 200，状态正常
- `POST /auth/register`（含 email）=> 201，返回 `access_token`（契约已生效）
- `POST /auth/register`（缺 email）=> 422（符合“email 必填”）
- `POST /api/v1/medication/parse-nlp`（无 token）=> 401（鉴权生效）
- `POST /api/v1/medication/parse-nlp`（带 token）=> 200，返回 `mentioned_meds/actions/questions`

## 发现与风险
- `HEI-agent` 位于 OneDrive 路径，存在间歇性文件读取超时（`Operation timed out`）。
- 该问题会影响 `docker compose` 直接读取项目目录文件；本次通过 `docker run` 启动依赖容器绕过。
- 启动日志存在 socks proxy 相关 warning（`socksio` 缺失），不影响本阶段核心接口验证。

## 下一阶段（Phase 2）
1. Android 侧同步改造（注册 UI 强制 email、用药接口按后端结构）
2. Sync v2 协议落地（push/pull/cursor/version/tombstone/conflict）
3. 增补后端集成测试（sync 冲突与幂等）
4. 联调 Android DataSyncManager 双向回放链路
