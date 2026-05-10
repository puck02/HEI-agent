# HEI-agent 记忆系统设计说明

> 面向面试讲解：解释 `MEMORY.md`、`USER.md`、SQLite 记忆表、会话历史与 System Prompt 如何协同，让健康管家具备“长期个性化 + 跨会话召回 + 当前对话连续性”。

## 1. 一句话概括

HEI-agent 的记忆系统采用三层设计：

1. **USER.md**：用户档案，记录稳定、长期不变或很少变化的用户画像，例如姓名、基础偏好、健康背景；
2. **MEMORY.md**：Agent 笔记，记录模型在对话中主动沉淀的重要事实，例如过敏史、饮食偏好、生活习惯；
3. **SQLite**：结构化长期记忆与会话摘要，用于关键词检索和跨会话召回。

每次对话开始时，系统会把 `USER.md` 和 `MEMORY.md` 注入到 System Prompt 中；当模型需要更细的历史事实或过往对话时，再通过工具调用 `search_memory` / `search_sessions` 去 SQLite 中检索。

---

## 2. 为什么不是只用一种记忆？

如果只用 prompt 注入，问题是上下文长度有限，记忆越多越容易膨胀；如果只用数据库检索，问题是模型每轮都不知道用户的基础画像，必须频繁搜索。

所以项目里做了分层：

| 层级 | 存储形式 | 作用 | 是否每轮注入 Prompt | 是否可检索 |
|---|---|---|---|---|
| 用户档案 | `USER.md` | 稳定用户画像 | 是 | 否，主要直接注入 |
| Agent 笔记 | `MEMORY.md` | 高价值长期事实 | 是 | 间接同步到 SQLite 后可检索 |
| 长期记忆库 | SQLite `agent_memories` | 可搜索的事实库 | 否 | 是，`search_memory` |
| 会话摘要 | SQLite `agent_session_summaries` | 跨会话历史总结 | 否 | 是，`search_sessions` |
| 当前对话历史 | `SessionStore` 内存 | 当前 session 多轮上下文 | 是，作为 messages history | 不走 SQL |

这种设计的核心思想是：

- **小而重要的稳定信息**：直接进 Prompt；
- **可能很多、按需使用的信息**：放 SQLite，通过工具检索；
- **当前会话上下文**：直接作为 `conversation_history` 传给模型；
- **跨会话历史**：压缩成 summary，再通过关键词搜索。

---

## 3. 代码结构对应关系

核心文件：

```text
app/agent/chat_agent.py
  - SYSTEM_PROMPT
  - ChatAgent._build_system_prompt()
  - ReAct 工具调用循环

app/services/profile_service.py
  - 读写 USER.md / MEMORY.md
  - get_system_context() 负责拼接注入上下文

app/services/memory_service.py
  - SQLite 表初始化
  - agent_memories 长期事实
  - agent_session_summaries 会话摘要
  - LIKE 关键词搜索

app/agent/tools/memory_tool.py
  - search_memory()
  - remember()
  - search_sessions()

app/memory/session_store.py
  - demo 模式下的内存会话管理
  - 保存当前 session 的 user / assistant messages

app/main.py
  - /api/demo/chat
  - 从 SessionStore 取 conversation_history
  - 调用 ChatAgent.chat()
```

---

## 4. USER.md：用户档案层

### 4.1 作用

`USER.md` 用来保存用户稳定画像，类似“用户资料卡”。它适合放：

- 用户姓名、昵称；
- 年龄、性别等基础信息；
- 慢性病史、长期健康目标；
- 长期饮食偏好；
- 固定生活习惯；
- 长期用药背景；
- 用户希望 Agent 如何称呼自己。

它不适合放大量临时事实，比如“昨天头疼”“刚刚吃了布洛芬”，这类更适合健康日志、用药记录或 SQLite 记忆。

### 4.2 存储路径

代码中默认路径是：

```python
DEFAULT_PROFILE_DIR = Path.home() / ".hei-agent" / "profiles"
```

对于某个用户：

```text
~/.hei-agent/profiles/{user_id}/USER.md
```

例如 demo 用户理论路径：

```text
/home/admin/.hei-agent/profiles/demo_user/USER.md
```

### 4.3 读取方式

`ProfileService.get_profile(user_id)` 读取 `USER.md`：

```python
def get_profile(self, user_id: str) -> str:
    return self._read_file(user_id, "USER.md")
```

然后在 `get_system_context()` 中拼成：

```text
## USER.md (用户档案)

{USER.md 内容}
```

### 4.4 USER.md 的定位

面试时可以这样说：

> USER.md 是静态用户档案，主要保存长期稳定的人设和基础信息，每轮对话都会注入 System Prompt。这样模型不需要每次都搜索数据库，也能天然知道用户是谁、有什么长期偏好和健康背景。

---

## 5. MEMORY.md：Agent 笔记层

### 5.1 作用

`MEMORY.md` 是 Agent 自己沉淀的“长期笔记”。它记录的是模型认为之后还会用到的重要事实，例如：

```text
- 用户对青霉素过敏
- 用户晚上喝咖啡容易失眠
- 用户偏好低盐饮食建议
- 用户近期关注血压管理
```

和 `USER.md` 的区别：

| 对比项 | USER.md | MEMORY.md |
|---|---|---|
| 维护者 | 用户/开发者手动维护为主 | Agent 通过 remember 工具追加 |
| 内容性质 | 静态画像 | 对话中沉淀的事实 |
| 更新频率 | 低 | 中等，随对话增长 |
| 注入方式 | 每轮注入 | 每轮注入 |

### 5.2 写入方式

`remember` 工具会同时写两处：

1. SQLite `agent_memories`；
2. 文件 `MEMORY.md`。

代码在 `app/agent/tools/memory_tool.py`：

```python
async def remember(user_id: str, fact: str) -> str:
    # Store in SQLite
    service = MemoryService()
    memory_id = await service.remember(
        user_id=user_id,
        content=fact,
        memory_type="user_fact",
        importance=0.7,
    )

    # Also append to MEMORY.md
    profile = ProfileService()
    profile.add_memory_fact(user_id, fact)
```

`ProfileService.add_memory_fact()` 会追加成 Markdown bullet：

```python
def add_memory_fact(self, user_id: str, fact: str) -> None:
    line = f"- {fact}"
    self._append_to_file(user_id, "MEMORY.md", line)
```

### 5.3 为什么同时写 SQLite 和 MEMORY.md？

这是设计重点：

- 写入 `MEMORY.md`：让高价值事实每轮都能直接被模型看到；
- 写入 SQLite：让事实可以被关键词检索、排序、限制 top_k，不必把所有历史都塞进 prompt。

也就是说，`MEMORY.md` 是“常驻上下文”，SQLite 是“可搜索记忆库”。

### 5.4 MEMORY.md 控制膨胀

`ProfileService` 里有 `compact_memory()`：

```python
def compact_memory(self, user_id: str, max_lines: int = 50) -> None:
    lines = self.get_memory_lines(user_id)
    if len(lines) <= max_lines:
        return
    self.write_memory(user_id, "\n".join(lines[-max_lines:]))
```

它的思路是保留最近的若干条，避免 prompt 注入无限增长。

---

## 6. SQLite：可检索长期记忆与会话摘要

SQLite 层由 `app/services/memory_service.py` 管理。

### 6.1 表结构

启动时通过 `_ensure_tables()` 创建两张核心表。

#### agent_memories

```sql
CREATE TABLE IF NOT EXISTS agent_memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    memory_type TEXT DEFAULT 'general',
    importance REAL DEFAULT 0.5,
    created_at TEXT NOT NULL
)
```

用途：保存长期事实。

字段解释：

| 字段 | 含义 |
|---|---|
| id | UUID，记忆唯一 ID |
| user_id | 用户 ID，用于隔离不同用户 |
| content | 记忆正文，例如“用户对青霉素过敏” |
| memory_type | 类型，例如 `user_fact` |
| importance | 重要性分数，当前 remember 默认 0.7 |
| created_at | 创建时间 |

#### agent_session_summaries

```sql
CREATE TABLE IF NOT EXISTS agent_session_summaries (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
)
```

用途：保存历史会话摘要，支持用户说“上次我们聊的那个……”时进行跨会话召回。

### 6.2 索引

代码创建了三个索引：

```sql
CREATE INDEX IF NOT EXISTS idx_memories_user
ON agent_memories(user_id)

CREATE INDEX IF NOT EXISTS idx_memories_user_type
ON agent_memories(user_id, memory_type)

CREATE INDEX IF NOT EXISTS idx_session_summaries_user
ON agent_session_summaries(user_id)
```

这些索引用于按用户过滤记忆，避免不同用户记忆混在一起。

### 6.3 搜索方式：关键词 LIKE

当前不是向量检索，也不是 BM25，而是轻量级关键词 LIKE：

```python
terms = [t.strip() for t in keywords.split() if t.strip()]
conditions = " OR ".join(f"content LIKE :t{i}" for i in range(len(terms)))
```

SQL 逻辑：

```sql
SELECT id, content, memory_type, importance, created_at
FROM agent_memories
WHERE user_id = :uid AND (content LIKE :t0 OR content LIKE :t1 ...)
ORDER BY created_at DESC
LIMIT :lim
```

特点：

- 简单、可解释、低成本；
- 不依赖 embedding；
- 适合 demo 和轻量级个人助手；
- 缺点是召回依赖关键词，语义相近但字面不同可能搜不到。

### 6.4 search_memory 工具

`search_memory(user_id, keywords)` 返回最多 5 条长期记忆：

```python
results = await service.search_memory(user_id=user_id, keywords=keywords, top_k=5)
```

返回格式类似：

```text
Found 1 memories:
  #1 [user_fact] (2026-05-09) 用户对青霉素过敏
```

### 6.5 search_sessions 工具

`search_sessions(user_id, keywords)` 搜索历史会话摘要，最多返回 3 条：

```python
results = await service.search_sessions(user_id=user_id, keywords=keywords, top_k=3)
```

适合场景：

- 用户说“上次你说那个药怎么吃来着？”；
- 用户说“之前我们聊过我的睡眠问题”；
- 用户引用跨 session 的上下文。

---

## 7. 当前会话历史：SessionStore

除了长期记忆，HEI-agent demo 还维护当前 session 的短期对话历史。

文件：

```text
app/memory/session_store.py
```

结构：

```python
self._sessions: dict[str, dict] = {}
```

每个 session：

```python
{
    "session_id": session_id,
    "title": title or "新对话",
    "created_at": now,
    "updated_at": now,
    "messages": [],
}
```

每条 message：

```python
{
    "role": role,
    "content": content,
    "timestamp": now,
}
```

在 `/api/demo/chat` 中：

1. 根据 `session_id` 找 session；
2. 取出历史 messages；
3. 转成 OpenAI 消息格式；
4. 保存当前 user message；
5. 调用 `ChatAgent.chat(..., conversation_history=conversation_history)`；
6. 保存 assistant response。

代码逻辑：

```python
raw_history = store.get_messages(session_id)
conversation_history = [
    {"role": m["role"], "content": m["content"]}
    for m in raw_history
]

store.add_message(session_id, "user", message)

result = await agent.chat(
    user_id="demo_user",
    session_id=session_id,
    message=message,
    conversation_history=conversation_history,
)

store.add_message(session_id, "assistant", answer_text)
```

这解决的是“当前对话连续性”，例如用户上一轮说“我吃的是阿莫西林”，下一轮只说“250mg”，模型仍然能理解上下文。

> 注意：这个 demo SessionStore 是内存存储，服务重启后会丢失；长期事实仍应靠 MEMORY.md / SQLite 保存。

---

## 8. 三层记忆如何协调

### 8.1 每轮对话开始：构建 System Prompt

入口在 `ChatAgent.chat()`：

```python
messages = [{"role": "system", "content": self._build_system_prompt(user_id)}]
```

`_build_system_prompt()`：

```python
def _build_system_prompt(self, user_id: str) -> str:
    user_context = f"当前用户ID: {user_id}\n\n"
    context = self._profile.get_system_context(user_id)
    if context:
        return user_context + SYSTEM_PROMPT + "\n\n---\n\n" + context
    return user_context + SYSTEM_PROMPT
```

最终 System Prompt 结构：

```text
当前用户ID: demo_user

{基础 SYSTEM_PROMPT：Kitty 健康管家角色、工具规则、记忆规则...}

---

## USER.md (用户档案)

{USER.md 内容}

## MEMORY.md (Agent 笔记)

{MEMORY.md 内容}
```

### 8.2 再追加当前会话历史

```python
if conversation_history:
    messages.extend(conversation_history)
```

于是传给 LLM 的 messages 大致是：

```text
system: 基础 prompt + USER.md + MEMORY.md
user: 当前 session 第 1 轮用户消息
assistant: 当前 session 第 1 轮回复
user: 当前 session 第 2 轮用户消息
assistant: 当前 session 第 2 轮回复
user: 当前最新消息
```

### 8.3 如果需要更多历史事实，调用工具搜索 SQLite

基础 prompt 里明确告诉模型：

```text
当用户提到与个人相关的话题（如过敏史、用药偏好、生活习惯），使用 search_memory(keywords="关键词") 搜索

search_memory 只用于搜索「用户个人」的事实和偏好，如 "青霉素 过敏"、"咖啡 偏好"

search_sessions(keywords) 可以搜索过往对话摘要
```

所以模型决策逻辑是：

- 当前 prompt 中已经有 USER.md / MEMORY.md：直接使用；
- 如果用户问的是个人历史相关，但 prompt 中不够明确：调用 `search_memory`；
- 如果用户提到“上次”“之前聊过”：调用 `search_sessions`；
- 如果问的是医学知识：调用 `search_health` / `search_medication` / `search_tcm`，而不是 search_memory。

---

## 9. 对应 Prompt 设计

### 9.1 基础系统 Prompt 中和记忆相关的部分

`app/agent/chat_agent.py` 中 `SYSTEM_PROMPT` 的核心记忆规则是：

```text
你可以访问用户的健康日报、用药记录和长期记忆，非常了解用户的身体状况

当用户提到与个人相关的话题（如过敏史、用药偏好、生活习惯），使用 search_memory(keywords="关键词") 搜索

⚠️ 记忆系统说明：
- 你的系统提示词中已经包含了 USER.md（用户档案）和 MEMORY.md（你的笔记）
- search_memory 只用于搜索「用户个人」的事实和偏好，如 "青霉素 过敏"、"咖啡 偏好"
- 需要健康/药品/中医知识时，优先使用 search_health / search_medication / search_tcm
- search_sessions(keywords) 可以搜索过往对话摘要
- 如果用户只是闲聊或询问通用问题，不需要调用任何工具
```

这段 prompt 的作用是给模型做“路由约束”：

- 个人事实 → `search_memory`
- 过往对话 → `search_sessions`
- 医学知识 → RAG 知识库工具
- 普通闲聊 → 不调用工具

### 9.2 日报分析 Prompt

日报场景下，System Prompt 还写了专门流程：

```text
📋 日报分析流程（当用户提交包含「日报」和「建议」的健康数据时）：
1. 先并行调用 read 工具：search_memory(keywords="睡眠 饮食 运动 血压...") 查用户历史
   + search_health(query="...") / search_medication(query="...") 查知识库
2. 综合分析：日报数据 + 记忆中的用户画像 + 知识库建议 → 给出个性化健康建议
```

这对应代码里的 `_two_phase_chat()`：

1. Phase 1：LLM 带工具，决定要查什么；
2. 执行 read tools；
3. Phase 2：把工具结果作为用户上下文，再让 LLM 生成完整建议。

二阶段合成 prompt：

```python
messages.append({
    "role": "user",
    "content": (
        f"系统已经为你检索了以下辅助信息来帮助分析日报：\n\n"
        f"{tool_outputs}\n\n"
        f"请基于用户的日报数据和上述检索结果，用Kitty的语气给出个性化、专业、温暖的健康建议。"
    ),
})
```

### 9.3 普通检索后的合成 Prompt

ReAct 循环中，如果执行了 read tools，会追加：

```python
messages.append({
    "role": "user",
    "content": (
        f"系统已为你检索了以下辅助信息：\n\n"
        f"{tool_outputs}\n\n"
        f"请综合这些信息，用Kitty的语气给用户一个完整、专业、温暖的回答。"
        f"不要只是罗列信息，要结合用户的问题给出个性化建议。"
    ),
})
```

这保证工具结果不是直接裸返回，而是再经过模型整合成自然回答。

---

## 10. 写入记忆的确认机制

`remember` 是写工具，因此在 ToolRegistry 中被标记为 write tool：

```python
WRITE_TOOL_NAMES = {
    "add_medication", "update_medication", "remove_medication",
    "log_health", "remember",
}
```

写工具不会立即执行，而是先进入 pending 状态：

```python
self.registry.set_pending(write_name, write_args)
return {
    "answer": self._build_confirmation_message(write_name, write_args),
    "needs_confirmation": True,
    "pending_tool": write_name,
}
```

用户确认后才执行：

```python
pending = self.registry.get_pending()
is_confirmation = self._is_confirmation(message)

if pending and is_confirmation:
    result = await self.registry.execute_write_tool(tool_call)
    self.registry.clear_pending()
```

确认词包括：

```python
{"确认", "好的", "可以", "行", "yes", "ok", "confirm", "好", "嗯", "对", "是的", "没错", "执行"}
```

所以记忆写入流程是：

```text
用户：记住我对青霉素过敏
  ↓
预路由 / LLM 识别 remember 写工具
  ↓
系统返回确认请求
  ↓
用户：确认
  ↓
execute_write_tool(remember)
  ↓
SQLite agent_memories 插入一条 user_fact
  ↓
MEMORY.md 追加一行 - 用户对青霉素过敏
```

这样能避免模型误把敏感或错误信息直接写入长期记忆。

---

## 11. 示例：用户过敏史如何被记住和使用

### 11.1 写入

用户说：

```text
记住我对青霉素过敏
```

系统识别为 `remember` 写工具，要求确认。

用户确认后，SQLite 写入：

```text
agent_memories:
  user_id = demo_user
  content = 用户对青霉素过敏
  memory_type = user_fact
  importance = 0.7
```

同时 `MEMORY.md` 追加：

```md
- 用户对青霉素过敏
```

### 11.2 后续使用：直接注入

下一轮对话开始时，System Prompt 包含：

```md
## MEMORY.md (Agent 笔记)

- 用户对青霉素过敏
```

如果用户问：

```text
我能吃阿莫西林吗？
```

模型在 prompt 里已经看到过敏史，应提醒：阿莫西林属于青霉素类抗生素，用户有青霉素过敏史，不建议自行服用，应咨询医生。

### 11.3 后续使用：工具检索

如果 `MEMORY.md` 变大或相关事实不在 prompt 中，模型可调用：

```text
search_memory(keywords="青霉素 过敏")
```

返回：

```text
Found 1 memories:
  #1 [user_fact] (2026-05-09) 用户对青霉素过敏
```

再综合回答。

---

## 12. 三类记忆的职责边界

### 12.1 USER.md 放什么

适合：

```md
name: 张三
age: 28
health_goal: 控制血压，改善睡眠
preference: 喜欢简短、可执行的建议
chronic_conditions: 高血压
```

不适合：

```md
昨天晚上 11 点睡觉
今天喝了一杯咖啡
刚才说头疼
```

这些更适合健康日志或会话历史。

### 12.2 MEMORY.md 放什么

适合：

```md
- 用户对青霉素过敏
- 用户不喜欢太复杂的饮食建议，希望给出简单可执行清单
- 用户晚间喝咖啡容易影响睡眠
```

不适合：

```md
- 用户刚刚问了一个问题
- 用户今天说你好
- 用户这轮对话提到“嗯”
```

### 12.3 SQLite 放什么

适合：

- 所有长期事实的结构化副本；
- 会话摘要；
- 可搜索历史。

SQLite 更像“检索型记忆库”，不是每轮都塞进 prompt。

### 12.4 SessionStore 放什么

适合：

- 当前打开的聊天窗口内的完整多轮上下文；
- 用户刚刚说过但不值得长期保存的信息；
- 追问流程中的临时状态。

服务重启后会丢，所以不负责长期记忆。

---

## 13. 面试讲法

可以这样讲：

> 我把健康管家的记忆分成三层。第一层是 USER.md，保存用户稳定画像，比如基础健康背景和长期偏好，每轮都会注入 System Prompt；第二层是 MEMORY.md，保存 Agent 在对话中沉淀的高价值事实，比如过敏史、饮食偏好，也会每轮注入；第三层是 SQLite，保存结构化长期记忆和会话摘要，通过 search_memory 和 search_sessions 做关键词召回。这样常用、高价值的信息能直接进入上下文，而大量历史信息按需检索，避免 prompt 无限膨胀。

如果面试官追问“为什么 MEMORY.md 和 SQLite 都要写？”可以回答：

> MEMORY.md 是常驻上下文，保证关键事实不需要检索也能被模型看到；SQLite 是可检索记忆库，适合存更多历史事实和会话摘要。写入 remember 时我同时写两边：一边保证即时个性化，一边支持后续关键词召回。

如果面试官追问“怎么避免乱写记忆？”可以回答：

> remember 是写工具，被 ToolRegistry 标记为 write tool。写工具不会直接执行，而是先进入 pending 状态，系统向用户确认。只有用户回复“确认/好的/可以”等确认词后，才真正写入 SQLite 和 MEMORY.md。

如果面试官追问“当前对话上下文怎么处理？”可以回答：

> 当前 session 的 user/assistant messages 存在 SessionStore 中，每次 `/api/demo/chat` 会取出历史消息，转成 conversation_history 注入 ChatAgent。这样模型能理解本轮对话里的省略和追问；而跨会话则依赖 SQLite 的 session summary 搜索。

---

## 14. 当前实现的边界

这个设计是轻量 demo 版本，也有明确边界：

1. SQLite 搜索是 `LIKE` 关键词匹配，不是向量检索；
2. `SessionStore` 是内存存储，服务重启后当前会话历史会丢；
3. `agent_session_summaries` 表和接口已经设计，但是否自动生成摘要要看后续流程是否接入；
4. `MEMORY.md` 每轮注入，内容过多会增加 token，需要 compact；
5. `USER.md` 主要由用户/开发者维护，不适合频繁自动改写。

这些边界可以坦诚说明，反而显得你知道工程取舍。

---

## 15. 简历可写法

如果要把这块写进简历，可以压缩成：

```text
设计分层记忆系统：USER.md 保存稳定用户画像，MEMORY.md 保存 Agent 沉淀的高价值长期事实，并在每轮对话中注入 System Prompt；SQLite 持久化 agent_memories 与 agent_session_summaries，通过 search_memory/search_sessions 支持关键词召回；当前会话历史由 SessionStore 注入 conversation_history，支持多轮追问和跨会话个性化。
```

更短版：

```text
设计 USER.md + MEMORY.md + SQLite 的分层记忆机制：高价值画像直接注入 Prompt，长期事实与会话摘要持久化并按需检索，结合 SessionStore 实现当前会话连续性与跨会话召回。
```
