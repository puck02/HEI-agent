# AgentOps C++ 日志检索与异常诊断工具 Implementation Plan

> **For Hermes:** 当前阶段只做规划，不实现代码。后续实现时建议使用 `subagent-driven-development` 或 Claude Code 分阶段开发，并进行全链路测试。

**Goal:** 构建一个兼顾通用性与 HEI-agent 场景的 C++17 日志检索与异常诊断 CLI 工具：底层是通用日志扫描/索引/规则引擎，上层通过规则包适配 AgentOps、LLM Provider、Qdrant、前后端服务、健康检查等场景。

**Architecture:** 采用“通用核心 + 可配置规则包 + 场景模板”的设计。核心模块不依赖 HEI-agent，只负责日志读取、多线程分片扫描、字段解析、倒排索引、规则匹配、时间窗口聚合和报告生成；HEI-agent/AgentOps 相关逻辑放在规则配置与 profile 中，作为一个内置诊断场景。

**Tech Stack:** C++17, CMake, Linux, STL, std::thread, std::regex, JSON, CLI, Markdown report, optional mmap/read benchmark.

---

## 1. 项目定位

### 1.1 简历定位

项目名称建议：

**面向 AgentOps 的 C++日志检索与异常诊断工具**

更通用一点的 GitHub 项目名：

```text
logscope-cpp
```

或：

```text
agent-log-doctor
```

简历上强调：

- C++17 工程能力；
- Linux 大文件日志处理；
- 多线程分片扫描；
- 倒排索引检索；
- 可扩展 ErrorRule 规则体系；
- AgentOps 场景适配；
- HEI-agent 部署日志验证。

### 1.2 真实需求来源

HEI-agent / Hermes 相关真实排障场景包括：

- 前端 Vite 502 / 页面无法访问；
- 后端 uvicorn 离线；
- Qdrant 容器连接失败或超时；
- DashScope embedding/rerank 失败；
- LLM Provider authentication failed；
- Hermes provider 配置错误；
- cron healthcheck 自动重启；
- API 500/502/timeout；
- 工具调用失败、RAG 检索失败。

但是项目不能只服务 HEI-agent，要抽象成：

> 任意 Linux 服务日志都可扫描；AgentOps 只是一个内置 profile。

---

## 2. 核心设计原则

### 2.1 通用核心，不写死业务

核心模块只认识这些通用概念：

```text
LogLine
LogEvent
ErrorRule
ScanResult
TimeWindowStats
SearchIndex
Report
```

不在核心代码里硬编码：

- HEI-agent；
- Qdrant；
- DashScope；
- Hermes；
- Vite；
- uvicorn。

这些放到规则包里。

### 2.2 Profile / Rule Pack 机制

支持不同规则包：

```text
profiles/
├── generic.json          # 通用 Linux/Web 服务规则
├── agentops.json         # Agent/LLM/RAG 服务规则
└── hei-agent.json        # HEI-agent 示例规则
```

CLI 使用方式：

```bash
logscope analyze logs/backend.log --profile agentops --report report.md
logscope analyze logs/*.log --profile hei-agent --json report.json
logscope search logs/backend.log --query "Provider authentication failed" --context 3
```

### 2.3 先做离线批处理，不做实时系统

MVP 不做：

- Web UI；
- 实时 tail -f；
- 分布式日志采集；
- ELK/Loki 替代品；
- AI 自动总结。

只做本地 CLI，保证能跑、能讲、能测试。

---

## 3. 功能边界

## 3.1 MVP 功能

必须实现：

1. 单文件/多文件日志扫描；
2. ERROR/WARN/INFO 级别识别；
3. 正则规则匹配；
4. 常见错误分类；
5. 错误 TopN；
6. 时间窗口聚合；
7. Markdown 报告；
8. JSON 报告；
9. AgentOps 规则包；
10. HEI-agent 示例日志和验证命令。

## 3.2 简历增强功能

建议实现：

1. 多线程分片扫描；
2. 分片边界对齐换行符；
3. 线程局部统计 + reduce merge；
4. 轻量倒排索引；
5. search 命令支持关键词查询；
6. 上下文片段返回；
7. benchmark 对比单线程/多线程；
8. 单元测试。

## 3.3 后续可选功能

可选，不作为第一版：

1. mmap 与 read buffer 性能对比；
2. 规则配置热加载；
3. HTML 报告；
4. Agent Tool JSON-RPC 接口；
5. 与 HEI-agent healthcheck 集成；
6. 简单异常趋势图；
7. 实时流式日志分析。

---

## 4. 目录结构规划

建议新建独立项目，不直接塞进 HEI-agent 主工程，避免污染原项目。

路径建议：

```text
/home/admin/workspace/logscope-cpp/
```

目录结构：

```text
logscope-cpp/
├── CMakeLists.txt
├── README.md
├── docs/
│   ├── design.md
│   ├── interview-notes.md
│   └── sample-report.md
├── include/
│   └── logscope/
│       ├── cli/Args.hpp
│       ├── core/LogLine.hpp
│       ├── core/LogEvent.hpp
│       ├── core/ScanResult.hpp
│       ├── scanner/LogScanner.hpp
│       ├── scanner/FileChunker.hpp
│       ├── rules/ErrorRule.hpp
│       ├── rules/RuleEngine.hpp
│       ├── index/InvertedIndex.hpp
│       ├── stats/TimeWindowAggregator.hpp
│       ├── report/JsonReport.hpp
│       └── report/MarkdownReport.hpp
├── src/
│   ├── main.cpp
│   ├── cli/Args.cpp
│   ├── scanner/LogScanner.cpp
│   ├── scanner/FileChunker.cpp
│   ├── rules/RuleEngine.cpp
│   ├── index/InvertedIndex.cpp
│   ├── stats/TimeWindowAggregator.cpp
│   ├── report/JsonReport.cpp
│   └── report/MarkdownReport.cpp
├── profiles/
│   ├── generic.json
│   ├── agentops.json
│   └── hei-agent.json
├── samples/
│   ├── generic_app.log
│   ├── agentops_backend.log
│   ├── hei_agent_backend.log
│   ├── hei_agent_healthcheck.log
│   └── qdrant.log
├── tests/
│   ├── test_rule_engine.cpp
│   ├── test_time_window.cpp
│   ├── test_inverted_index.cpp
│   └── test_scanner.cpp
├── benchmarks/
│   ├── generate_large_log.py
│   └── run_benchmark.sh
└── scripts/
    ├── build.sh
    ├── test.sh
    └── demo.sh
```

---

## 5. 数据模型设计

### 5.1 LogLine

```cpp
struct LogLine {
    std::string file;
    size_t line_number;
    std::string raw;
    std::string timestamp;   // 可为空
    std::string level;       // ERROR/WARN/INFO/UNKNOWN
};
```

### 5.2 ErrorRule

```cpp
struct ErrorRule {
    std::string id;
    std::string name;
    std::string category;
    std::string severity;    // LOW/MEDIUM/HIGH/CRITICAL
    std::regex pattern;
    std::string suggestion;
};
```

示例规则：

```json
{
  "id": "provider_auth_failed",
  "name": "Provider Authentication Failed",
  "category": "LLM_PROVIDER",
  "severity": "HIGH",
  "pattern": "Provider authentication failed|Unknown provider|401 Unauthorized",
  "suggestion": "检查 Hermes/应用配置中的 provider 名称、API Key 与 base_url 是否匹配。"
}
```

### 5.3 LogEvent

```cpp
struct LogEvent {
    LogLine line;
    std::string rule_id;
    std::string category;
    std::string severity;
};
```

### 5.4 ScanResult

```cpp
struct ScanResult {
    size_t total_lines;
    size_t error_count;
    size_t warn_count;
    std::unordered_map<std::string, size_t> category_counts;
    std::unordered_map<std::string, size_t> rule_counts;
    std::vector<LogEvent> events;
};
```

---

## 6. Profile 设计

### 6.1 generic.json

通用规则：

- HTTP 500；
- HTTP 502；
- timeout；
- connection refused；
- permission denied；
- out of memory；
- segmentation fault；
- disk full。

### 6.2 agentops.json

Agent/LLM/RAG 通用规则：

- provider authentication failed；
- unknown provider；
- model not found；
- context length exceeded；
- embedding failed；
- rerank failed；
- tool call failed；
- JSON parse failed；
- vector DB timeout；
- rate limit。

### 6.3 hei-agent.json

HEI-agent 示例规则：

- uvicorn 后端离线；
- Vite 前端 502；
- Qdrant connection refused；
- DashScope embedding batch size invalid；
- DashScope rerank input.query missing；
- Qdrant dimension mismatch；
- `/api/demo/chat` 500；
- healthcheck restarted backend/frontend/qdrant；
- Hermes provider config error。

注意：`hei-agent.json` 只是示例 profile，不应污染核心逻辑。

---

## 7. CLI 设计

### 7.1 analyze

```bash
logscope analyze <log-path...> \
  --profile agentops \
  --threads 4 \
  --window 5m \
  --report report.md \
  --json report.json
```

作用：扫描日志，匹配规则，输出诊断报告。

### 7.2 search

```bash
logscope search <log-path...> \
  --query "Provider authentication failed" \
  --context 3 \
  --top-k 20
```

作用：关键词检索，返回命中行和上下文。

### 7.3 index

```bash
logscope index <log-path...> --output index.bin
logscope search-index index.bin --query "qdrant timeout"
```

第一版可不持久化索引，只在内存中搜索；第二版再加持久化。

### 7.4 demo

```bash
scripts/demo.sh
```

应完成：

1. 构建项目；
2. 分析 `samples/hei_agent_backend.log`；
3. 生成 `out/report.md`；
4. 展示 TopN 错误和建议。

---

## 8. 报告设计

Markdown 报告结构：

```markdown
# LogScope Diagnosis Report

## Summary
- Files scanned: 3
- Total lines: 125,000
- ERROR: 132
- WARN: 421
- Time range: 2026-05-06 18:00 ~ 2026-05-06 20:00

## Top Error Categories
| Category | Count | Severity |
|---|---:|---|
| LLM_PROVIDER | 12 | HIGH |
| QDRANT | 8 | HIGH |
| HTTP_502 | 5 | MEDIUM |

## Timeline
| Window | ERROR | WARN |
|---|---:|---:|
| 18:00-18:05 | 2 | 4 |

## Diagnosis
### Provider Authentication Failed
- Count: 7
- Severity: HIGH
- Suggestion: 检查 provider 名称/API Key/base_url 是否匹配。
- Sample lines:
  - backend.log:123 Provider authentication failed...

## Recommended Next Steps
1. 检查 Hermes config.yaml 中 model.provider 是否是 provider 名称而不是 API Key。
2. 检查 Qdrant 容器是否运行：docker ps | grep qdrant
3. 检查后端 health：curl http://localhost:8000/health
```

---

## 9. 技术亮点规划

### 9.1 多线程分片扫描

设计：

1. 获取文件大小；
2. 按线程数切分字节范围；
3. 每个分片起点/终点移动到最近换行符；
4. 每个线程只处理完整日志行；
5. 每个线程维护局部统计；
6. 主线程 reduce merge。

面试可讲点：

- 避免日志行被两个线程切断；
- 局部统计减少锁竞争；
- 多线程对小文件不一定更快，要 benchmark；
- `std::regex` 可能成为瓶颈。

### 9.2 倒排索引

第一版内存结构：

```cpp
std::unordered_map<std::string, std::vector<Posting>> index;

struct Posting {
    std::string file;
    size_t line_number;
};
```

支持：

- 单关键词；
- 多关键词 AND 查询；
- 命中行上下文。

### 9.3 ErrorRule 规则体系

规则分层：

```text
Rule Pack -> ErrorRule -> Regex Pattern -> LogEvent -> Diagnosis
```

后续可扩展：

- JSON/YAML 配置；
- severity 权重；
- category 聚合；
- suggestion 模板。

### 9.4 时间窗口聚合

支持按分钟聚合：

```bash
--window 5m
```

用途：

- 找到错误爆发时间；
- 区分偶发错误和集中故障；
- 和 healthcheck 重启时间对齐。

---

## 10. 与 HEI-agent 的贴合方式

### 10.1 使用 HEI-agent 风格样例日志

样例日志应覆盖：

```text
Provider authentication failed: Unknown provider 'sk-xxx'
qdrant_client.http.exceptions.ConnectError: Connection refused
POST /api/demo/chat 500 Internal Server Error
GET /health 502 Bad Gateway
DashScope embedding failed: batch size should not be larger than 10
DashScope rerank failed: Field required: input.query
healthcheck: backend down, restarting uvicorn
healthcheck: frontend down, restarting vite
```

### 10.2 生成 AgentOps 报告

报告中能给出贴合 HEI-agent 的建议：

- Provider 报错：检查 Hermes `model.provider` 是否写成 API Key；
- Qdrant 报错：检查 `hel-qdrant` 容器和 6333 端口；
- 502：检查前端 Vite、后端 uvicorn、Vite proxy；
- DashScope batch：检查 embedding 批量是否 <=10；
- rerank input.query：检查 DashScope rerank API 是否使用 nested input 格式。

### 10.3 不绑定 HEI-agent

同一工具也能分析普通 Nginx / FastAPI / Java / Node 日志，只要切换 profile：

```bash
logscope analyze nginx.log --profile generic
logscope analyze backend.log --profile agentops
logscope analyze hei.log --profile hei-agent
```

---

## 11. 分阶段实现计划

## Phase 0: 需求冻结与项目初始化

**目标:** 明确范围，创建项目骨架。

**任务:**

1. 创建 `/home/admin/workspace/logscope-cpp/`；
2. 创建 CMake 项目；
3. 创建 README 初稿；
4. 创建 `samples/` 日志；
5. 创建 `profiles/` 三个规则文件；
6. 写清楚第一版不做 Web UI/实时采集。

**验证:**

```bash
cmake -S . -B build
cmake --build build
./build/logscope --help
```

---

## Phase 1: 单线程日志扫描 + 规则匹配

**目标:** 能扫描日志并识别规则。

**任务:**

1. 实现 `LogLine`；
2. 实现 `ErrorRule`；
3. 实现 `RuleEngine`；
4. 实现简单 profile 加载；
5. 实现单线程 `LogScanner`；
6. 统计 total/error/warn/rule_counts；
7. 输出终端摘要。

**验证:**

```bash
./build/logscope analyze samples/hei_agent_backend.log --profile profiles/hei-agent.json
```

预期：能识别 Provider/Qdrant/502/Timeout 等错误。

---

## Phase 2: Markdown/JSON 报告

**目标:** 生成可展示的诊断报告。

**任务:**

1. 实现 `JsonReport`；
2. 实现 `MarkdownReport`；
3. 报告包含 summary/top errors/sample lines/suggestions；
4. 添加 `--report` 和 `--json` 参数；
5. 写 `docs/sample-report.md`。

**验证:**

```bash
./build/logscope analyze samples/hei_agent_backend.log \
  --profile profiles/hei-agent.json \
  --report out/report.md \
  --json out/report.json
```

---

## Phase 3: 时间窗口聚合

**目标:** 支持按时间段统计错误爆发。

**任务:**

1. 实现常见时间戳解析；
2. 支持 ISO 格式、uvicorn 常见格式；
3. 实现 `TimeWindowAggregator`；
4. 支持 `--window 1m/5m/10m`；
5. 报告中输出 timeline 表格。

**验证:**

构造样例日志，确认 5 分钟窗口统计正确。

---

## Phase 4: 多线程分片扫描

**目标:** 增加 C++技术深度。

**任务:**

1. 实现 `FileChunker`；
2. 按文件大小切分 offset range；
3. 分片边界对齐换行符；
4. 每个线程扫描自己的 range；
5. 每个线程生成局部 `ScanResult`；
6. 主线程 merge；
7. 添加 `--threads N` 参数；
8. 小文件默认单线程，大文件启用多线程。

**验证:**

```bash
./build/logscope analyze samples/large.log --threads 1
./build/logscope analyze samples/large.log --threads 4
```

检查结果一致，记录耗时差异。

---

## Phase 5: 倒排索引与 search 命令

**目标:** 从“统计工具”升级为“日志检索工具”。

**任务:**

1. 实现 tokenizer；
2. 实现 `InvertedIndex`；
3. 建立 term -> posting list；
4. 实现单关键词查询；
5. 实现多关键词 AND 查询；
6. 支持 `--context N` 返回上下文行；
7. 支持 `--top-k N`。

**验证:**

```bash
./build/logscope search samples/hei_agent_backend.log \
  --query "Provider authentication failed" \
  --context 2
```

---

## Phase 6: 测试与 Benchmark

**目标:** 让项目简历可信。

**任务:**

1. 添加单元测试：RuleEngine；
2. 添加单元测试：TimeWindowAggregator；
3. 添加单元测试：InvertedIndex；
4. 添加集成测试：analyze sample log；
5. 编写 `generate_large_log.py`；
6. 编写 benchmark 对比单线程/多线程；
7. README 写入测试与性能结果。

**验证:**

```bash
scripts/test.sh
benchmarks/run_benchmark.sh
```

---

## Phase 7: 文档、简历材料、面试问答

**目标:** 项目能讲、能投简历。

**任务:**

1. README 添加项目背景；
2. README 添加架构图；
3. README 添加 demo 命令；
4. README 添加报告截图/片段；
5. `docs/interview-notes.md` 写面试问答；
6. 写简历 bullet；
7. 记录项目局限和后续优化。

---

## 12. 测试策略

### 12.1 单元测试

测试点：

- 规则匹配；
- severity/category 统计；
- 时间窗口聚合；
- 倒排索引查询；
- 分片边界处理。

### 12.2 集成测试

使用样例日志：

```bash
./build/logscope analyze samples/hei_agent_backend.log --profile profiles/hei-agent.json --json out/report.json
```

断言：

- total_lines 正确；
- provider_auth_failed count 正确；
- qdrant_connection_failed count 正确；
- report.md 存在；
- report.json 可解析。

### 12.3 性能测试

生成 100MB/500MB 模拟日志：

```bash
python3 benchmarks/generate_large_log.py --size 500M --output samples/large.log
```

对比：

- 单线程；
- 2线程；
- 4线程。

输出表格写入 README。

---

## 13. 简历写法草案

```text
面向 AgentOps 的 C++日志检索与异常诊断工具
技术栈：C++17 / Linux / Multithreading / Inverted Index / Regex / CMake

- 面向 AI Agent 服务运维场景，设计并实现本地日志检索与异常诊断 CLI，支持大文件扫描、关键词检索、异常归类和报告生成；
- 基于多线程分片扫描处理大规模日志，分片边界自动对齐换行符，并采用线程局部统计 + Reduce 合并方式降低锁竞争；
- 实现轻量级倒排索引，支持关键词组合查询、命中行定位和上下文片段返回，提高日志检索效率；
- 设计可扩展 ErrorRule 规则体系，自动识别 Provider 认证失败、Qdrant 连接异常、HTTP 502/500、Timeout 等常见故障；
- 支持按时间窗口聚合异常数量，输出 JSON/Markdown 诊断报告，包含错误 TopN、故障爆发时间段、疑似原因和排查建议；
- 在 HEI-agent 部署日志与模拟故障日志上验证工具有效性，用于辅助定位前后端服务离线、模型调用失败和向量数据库异常问题。
```

---

## 14. 面试讲法

### Q1: 为什么做这个项目？

答：

> 我在部署 HEI-agent 这类 Agent 应用时，遇到过前端 502、后端服务离线、Qdrant 连接失败、模型 Provider 配置错误等问题。手动 grep 日志只能查单个关键字，不方便统计错误频次、定位故障爆发时间，也不能沉淀排查经验。所以我做了一个 C++本地日志检索与诊断工具，把常见故障抽象成规则，自动生成诊断报告。

### Q2: 为什么用 C++？

答：

> 这个项目的核心是大文件扫描、字符串解析、多线程处理、倒排索引和本地 CLI 工具。C++适合实现低依赖、高性能的本地工具，也能更好地体现文件 IO、多线程、数据结构和 Linux 工程能力。业务规则通过 profile 配置，核心逻辑不绑定具体业务。

### Q3: 怎么兼顾通用性和 HEI-agent？

答：

> 我把系统分成通用核心和规则包。核心只处理日志行、规则匹配、统计、索引和报告；HEI-agent 相关的 Provider、Qdrant、healthcheck 等诊断逻辑都放在 `hei-agent.json` 规则包中。换成普通 Web 服务或其他 Agent 服务时，只要切换 profile 即可。

### Q4: 多线程扫描怎么避免切断日志行？

答：

> 文件按字节范围分片后，每个分片的起点和终点都会调整到最近的换行符，保证线程处理的是完整日志行。每个线程维护自己的局部统计结果，最后由主线程归并，减少锁竞争。

### Q5: 它和 grep/ELK 有什么区别？

答：

> grep 适合临时关键字搜索，但不能结构化统计和生成诊断建议；ELK/Loki 是完整日志平台，部署成本较高。我的工具定位是轻量级本地 CLI，用于个人项目、小型服务或离线日志包的快速诊断，强调低依赖、可配置规则和 AgentOps 场景适配。

---

## 15. 风险与取舍

### 风险 1: 项目显得像小工具

解决：必须实现多线程分片、倒排索引、规则引擎、时间窗口聚合，而不是只做正则统计。

### 风险 2: C++ regex 性能一般

解决：第一版使用 `std::regex` 简化实现，README 中注明后续可替换 RE2/Hyperscan 或自定义字符串匹配。

### 风险 3: 过度绑定 HEI-agent

解决：核心不写 HEI-agent 逻辑，通过 profile 实现适配。

### 风险 4: 做太大导致延期

解决：严格分 Phase，Phase 1-2 能跑，Phase 4-5 提升技术力，Phase 6-7 用于简历可信度。

---

## 16. 推荐开发节奏

### 第 1 周

目标：做出可运行 MVP。

- Phase 0；
- Phase 1；
- Phase 2；
- 初版 README。

### 第 2 周

目标：提升技术含量。

- Phase 3；
- Phase 4；
- Phase 5；
- 样例日志和 demo。

### 第 3 周

目标：吃透与简历化。

- Phase 6；
- Phase 7；
- benchmark；
- 面试问答；
- C++简历版本。

---

## 17. 最小可交付标准

写进简历前至少满足：

- [ ] 可通过 CMake 编译；
- [ ] `analyze` 命令可运行；
- [ ] `search` 命令可运行；
- [ ] 至少 3 个 profile：generic / agentops / hei-agent；
- [ ] 能识别至少 10 类错误；
- [ ] 能生成 Markdown/JSON 报告；
- [ ] 有多线程分片扫描；
- [ ] 有倒排索引；
- [ ] 有样例日志；
- [ ] 有测试脚本；
- [ ] 有 README 和 demo 命令；
- [ ] 你能讲清楚：为什么做、为什么 C++、如何通用化、如何贴合 AgentOps。

---

## 18. 后续是否接入 HEI-agent

第一版不直接改 HEI-agent。

后续可选接入方式：

```text
HEI-agent healthcheck.py
    ↓ 异常时收集日志
logscope analyze latest.log --profile hei-agent
    ↓ 生成诊断摘要
Hermes/QQ 通知用户
```

但这属于第二阶段，不影响项目本身作为独立 C++简历项目。
