# HEI-Agent 生产部署与运维说明

适用范围：当前 Docker Compose 部署（agent + postgres + redis + qdrant）

## 1. 上线前建议补齐的功能（按优先级）

### P0（建议上线前必须完成）

1. 健康检查与可观测性
- 保留并使用 /health 健康检查
- 增加 DB/Redis/Qdrant 子项状态输出（目前 /health 主要是应用与 LLM provider 状态）
- 在反向代理层配置健康探针与重启策略

2. 备份与恢复闭环
- PostgreSQL：定时逻辑备份（pg_dump）+ 定期恢复演练
- Redis：如果短期记忆对业务关键，保留 AOF 并定期复制 /data
- Qdrant：定期快照（collection snapshot）或卷级备份
- 明确 RPO/RTO（例如 RPO 24h，RTO 30min）

3. 日志可追踪
- 统一请求级 request_id/session_id/user_id 打点
- 错误日志分级与告警（至少 5xx、超时、LLM fallback）
- Docker 日志轮转，避免磁盘被日志打满

4. 安全基线
- 生产环境关闭 debug/docs
- 强 JWT 密钥、定期轮换
- 限制 CORS 白名单（不要 *）
- 反向代理启用 HTTPS

### P1（建议上线后 1-2 周内完成）

1. 监控与告警
- 指标：请求量、P95 延迟、错误率、Redis 命中、DB 连接池
- 告警：5xx 激增、容器重启频繁、磁盘利用率高、备份失败

2. 发布与回滚
- 固定镜像版本（避免 latest）
- 标准化回滚流程（镜像回滚 + 数据恢复策略）

3. 数据治理
- 增加数据保留策略（会话日志、备份保留周期）
- 隐私数据脱敏（日志中避免输出敏感内容）

### P2（可持续优化）

1. 灰度发布与压测
2. 多可用区/多实例高可用
3. 更细粒度的业务指标面板

---

## 2. 日志使用说明

## 2.1 当前可用日志入口

1. Docker 容器日志
- 查看全部服务：
  docker compose logs -f --tail=200
- 仅看 agent：
  docker compose logs -f --tail=200 agent

2. 本地开发日志文件
- 文件路径：logs/hei-agent.log
- 查看：
  tail -f logs/hei-agent.log

## 2.2 生产建议日志操作

1. 按错误筛选
- docker compose logs --since=30m agent | grep -i "error\|timeout\|failed"

2. 关键事件筛选
- chat 超时：grep chat_timeout
- memory 写入失败：grep bg_short_term_save_failed
- insight 抽取失败：grep bg_insight_extraction_failed

3. 日志轮转（强烈建议）
- 在 docker-compose.yml 的服务下增加 logging 配置，例如：
  logging:
    driver: json-file
    options:
      max-size: "10m"
      max-file: "5"

---

## 3. 备份与恢复说明

说明：以下命令默认在项目根目录执行（含 docker-compose.yml）。

## 3.0 脚本入口（推荐）

已提供三件套脚本：
- scripts/backup_all.sh：一键备份 PostgreSQL + Redis + Qdrant
- scripts/backup_prune.sh：按保留天数自动清理旧备份
- scripts/restore_all.sh：按备份目录执行恢复

首次使用：
- chmod +x scripts/backup_all.sh scripts/backup_prune.sh scripts/restore_all.sh

推荐备份方式：
- BACKUP_ROOT=./backups RETENTION_DAYS=14 PRUNE_AFTER_BACKUP=1 scripts/backup_all.sh

推荐恢复方式：
- scripts/restore_all.sh --backup-dir backups/2026-03-11_030000 --yes
- 若需先清空 PostgreSQL 再导入：
  scripts/restore_all.sh --backup-dir backups/2026-03-11_030000 --reset-postgres --yes

## 3.1 PostgreSQL 备份

1. 全库备份（SQL）
- mkdir -p backups/postgres
- docker compose exec -T postgres pg_dump -U helagent -d helagent > backups/postgres/helagent_$(date +%F_%H%M%S).sql

2. 仅结构备份
- docker compose exec -T postgres pg_dump -s -U helagent -d helagent > backups/postgres/schema_$(date +%F_%H%M%S).sql

## 3.2 PostgreSQL 恢复

1. 清库后恢复（谨慎）
- cat backups/postgres/helagent_xxx.sql | docker compose exec -T postgres psql -U helagent -d helagent

2. 恢复后校验
- docker compose exec -T postgres psql -U helagent -d helagent -c "SELECT count(*) FROM users;"

## 3.3 Redis 备份

当前 compose 已启用 AOF（redis-server --appendonly yes）并挂载 redis_data 卷。

建议额外做文件级备份：
1. 触发持久化
- docker compose exec -T redis redis-cli BGSAVE

2. 导出 redis 数据目录（AOF/RDB）
- mkdir -p backups/redis
- docker run --rm -v hei-agent_redis_data:/from -v "$PWD/backups/redis":/to alpine sh -c "cp -a /from/. /to/redis_data_$(date +%F_%H%M%S)"

## 3.4 Qdrant 备份

建议卷级备份（简单可靠）：
1. mkdir -p backups/qdrant
2. docker run --rm -v hei-agent_qdrant_data:/from -v "$PWD/backups/qdrant":/to alpine sh -c "cp -a /from/. /to/qdrant_data_$(date +%F_%H%M%S)"

## 3.5 自动化定时备份（crontab 示例）

每天凌晨 3 点执行一键备份 + 自动清理（示例）：
0 3 * * * cd /path/to/HEI-agent && BACKUP_ROOT=./backups RETENTION_DAYS=14 PRUNE_AFTER_BACKUP=1 scripts/backup_all.sh >> logs/backup_cron.log 2>&1

每周日凌晨 4 点执行清理（可选，和上面二选一）：
0 4 * * 0 cd /path/to/HEI-agent && BACKUP_ROOT=./backups RETENTION_DAYS=14 scripts/backup_prune.sh >> logs/backup_cron.log 2>&1

建议配套：
- 备份保留 7/14/30 天策略
- 每周做一次恢复演练
- 备份后做完整性校验（文件非 0、可恢复）

---

## 4. 生产部署最小检查清单

1. 环境变量
- APP_ENV=production
- DEBUG=false
- 强随机 JWT_SECRET_KEY
- 正确的 DATABASE_URL/REDIS_URL/QDRANT_URL
- 至少一个可用 LLM provider key

2. 网络与安全
- 反向代理 HTTPS
- 限制 CORS 域名
- 防火墙仅开放必要端口

3. 运维可用性
- docker compose ps 全部 healthy
- 最近 24h 无持续 error 峰值
- 最近一次备份成功且可恢复

---

## 5. 已完成项（本仓库）

1. docker-compose.yml 已增加日志轮转（agent/postgres/redis/qdrant）
2. 已提供 backup_all.sh / backup_prune.sh / restore_all.sh
3. 已提供可直接复制的 cron 示例

## 6. 建议你下一步做的两件事

1. 立刻做一次“恢复演练”（不要只备份不恢复）
2. 接入告警（备份失败、5xx激增、容器重启频繁）