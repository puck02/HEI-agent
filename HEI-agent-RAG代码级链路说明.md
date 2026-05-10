# HEI-agent RAG 系统代码级链路说明

> 基于当前项目代码整理：`/home/admin/workspace/HEI-agent`
> 重点文件：`app/rag/ingest.py`、`app/rag/engine.py`、`app/rag/engine_qdrant.py`、`app/llm/router.py`、`app/config.py`

---

## 1. 一句话概括

HEI-agent 的 RAG 链路是：

```text
Markdown/PDF/TXT 知识文件
  → 读取文本
  → RecursiveCharacterTextSplitter 按中文标点/段落递归切分
  → DashScope text-embedding-v4 生成 dense 向量
  → 轻量 lexical sparse encoder 生成 sparse 向量
  → 写入 Qdrant 三个 Hybrid collection（dense + sparse）
  → 用户 query 先做 LLM query rewrite
  → retrieval_query 同时生成 dense query vector 和 sparse query vector
  → Qdrant 原生 Hybrid Search：dense prefetch + sparse prefetch + RRF fusion
  → 多 collection 合并排序
  → DashScope gte-rerank 重排
  → 返回 top_k chunk 给 Agent / LLM
```

---

## 2. 知识库来源

知识库目录：

```text
data/knowledge/
```

当前知识库分三类：

```text
data/knowledge/health/
data/knowledge/medication/
data/knowledge/tcm/
```

对应 Qdrant 中的三个 collection：

```python
COLLECTIONS = {
    "health": "health_knowledge",
    "medication": "medication_info",
    "tcm": "tcm_wellness",
}
```

当前 Qdrant 实际数据量：

```text
health_knowledge    68 chunks
medication_info     37 chunks
tcm_wellness        669 chunks
总计                774 chunks
```

向量维度与检索 schema：

```text
dense vector: 1024 维，Cosine，字段名 dense
sparse vector: lexical sparse vector，字段名 sparse
fusion: Qdrant RRF
```

---

## 3. 文档加载策略

代码位置：

```text
app/rag/ingest.py
```

支持的文件类型：

```python
LOADERS = {
    ".txt": _load_text,
    ".md": _load_text,
    ".pdf": _load_pdf,
}
```

### 3.1 Markdown / TXT 加载

```python
def _load_text(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8")
```

也就是直接用 UTF-8 读取全文。

### 3.2 PDF 加载

```python
def _load_pdf(file_path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(file_path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)
```

PDF 使用 `pypdf` 按页抽取文本，再用两个换行拼接。

---

## 4. 文本切分策略

代码位置：

```text
app/rag/ingest.py
```

核心代码：

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=settings.rag_chunk_size,
    chunk_overlap=settings.rag_chunk_overlap,
    separators=["\n\n", "\n", "。", "；", "，", " ", ""],
)
chunks = splitter.split_text(text)
```

配置位置：

```text
app/config.py
```

当前配置：

```python
rag_chunk_size: int = 800
rag_chunk_overlap: int = 200
```

也就是说：

```text
chunk_size = 800
chunk_overlap = 200
```

需要注意：这里使用的是 `langchain_text_splitters` 这个独立文本切分组件，属于 LangChain 生态的一部分；但这不代表项目仍在使用 LangGraph 多 Agent 编排。HEI-agent 重构后，Agent 编排层已经从 LangGraph 多 Agent 改成了单 Agent + ReAct + Tools，RAG 入库阶段只是复用了一个文本预处理工具。

可以这样表述：

> Agent 架构层不再使用 LangGraph；RAG 文本预处理阶段使用 `langchain_text_splitters.RecursiveCharacterTextSplitter` 做递归字符切分。

---

## 5. RecursiveCharacterTextSplitter 的源码级切分逻辑

项目使用的是 `langchain_text_splitters` 中的 `RecursiveCharacterTextSplitter`。它不是简单硬切，也不是“到 800 字符后往前找最近标点”。

更准确地说，它的逻辑是：

```text
选择当前文本中存在的最高优先级分隔符
  → 用该分隔符把文本 split 成多个小段
  → 小段如果仍然超过 chunk_size，就递归使用下一级分隔符继续切
  → 小段如果小于 chunk_size，就进入 good_splits
  → 最后把 good_splits merge 成接近 chunk_size 的 chunks
  → merge 过程中通过 chunk_overlap 保留上下文重叠
```

分隔符优先级：

```python
["\n\n", "\n", "。", "；", "，", " ", ""]
```

含义是：

1. 优先按段落切：`\n\n`
2. 如果段落内部仍然太长，再按换行切：`\n`
3. 如果还太长，再按中文句号切：`。`
4. 再按分号切：`；`
5. 再按逗号切：`，`
6. 再按空格切：` `
7. 最后实在无法切开，才按字符级兜底：`""`

### 5.1 源码核心：先选择可用分隔符

`split_text()` 内部调用：

```python
def split_text(self, text: str) -> list[str]:
    return self._split_text(text, self._separators)
```

`_split_text()` 会从 separators 前往后找当前文本中存在的第一个分隔符：

```python
separator = separators[-1]
new_separators = []
for i, s_ in enumerate(separators):
    separator_ = s_ if self._is_separator_regex else re.escape(s_)
    if not s_:
        separator = s_
        break
    if re.search(separator_, text):
        separator = s_
        new_separators = separators[i + 1:]
        break
```

解释：

- 如果文本中有 `\n\n`，就先选 `\n\n`；
- 如果没有 `\n\n` 但有 `\n`，就选 `\n`；
- 如果没有换行但有 `。`，就选 `。`；
- 以此类推；
- `new_separators` 保存的是当前分隔符之后的低一级分隔符，用于递归处理过长片段。

### 5.2 按选中的分隔符 split

选好 separator 后，会调用：

```python
splits = _split_text_with_regex(
    text, separator_, keep_separator=self._keep_separator
)
```

如果 separator 是 `。`，效果类似：

```python
re.split("。", text)
```

如果 separator 是空字符串 `""`，就会变成字符级切分：

```python
list(text)
```

### 5.3 过长片段递归切分

split 后，每个片段会判断长度：

```python
for s in splits:
    if self._length_function(s) < self._chunk_size:
        good_splits.append(s)
    else:
        if good_splits:
            merged_text = self._merge_splits(good_splits, separator_)
            final_chunks.extend(merged_text)
            good_splits = []
        if not new_separators:
            final_chunks.append(s)
        else:
            other_info = self._split_text(s, new_separators)
            final_chunks.extend(other_info)
```

解释：

- 小于 `chunk_size=800` 的片段会先放进 `good_splits`；
- 如果某个片段本身大于等于 800，会继续调用 `_split_text(s, new_separators)`；
- 也就是用下一级分隔符继续切；
- 只有在没有更细分隔符时，才会保留这个过长片段。

### 5.4 小片段 merge 成 chunk

小片段不是直接返回，而是通过 `_merge_splits()` 合并成尽量接近 `chunk_size` 的 chunk：

```python
if total + len_ + separator_len > self._chunk_size:
    doc = self._join_docs(current_doc, separator)
    docs.append(doc)

    while total > self._chunk_overlap or (
        total + len_ + separator_len > self._chunk_size
        and total > 0
    ):
        total -= self._length_function(current_doc[0]) + separator_len
        current_doc = current_doc[1:]
```

解释：

- 逐个把 split 后的小片段加入当前 chunk；
- 如果再加入一个片段会超过 800，就先输出当前 chunk；
- 然后从当前 chunk 开头移除一部分旧片段；
- 保留一部分尾部内容作为 overlap；
- 继续加入后续片段，形成下一个 chunk。

这里的 `chunk_overlap=200` 不是严格保留最后 200 个字符，而是按 split 单元近似保留，所以实际 overlap 可能略大或略小。

### 5.5 举例说明

假设文本结构是：

```text
段落A 300字

段落B 1200字

段落C 200字
```

第一层会优先用 `\n\n` 切成：

```text
A: 300字
B: 1200字
C: 200字
```

处理过程：

- A 小于 800，进入 `good_splits`；
- B 大于 800，触发递归，用下一级分隔符继续切，比如 `\n`、`。`、`；`、`，`；
- C 小于 800，进入 `good_splits`；
- 最后把这些小片段 merge 成多个接近 800 字符、且带 200 左右 overlap 的 chunk。

所以它不是简单从第 800 个字符往前找标点，而是：

```text
按分隔符 split → 过长片段递归细切 → 小片段 merge → overlap 保留上下文
```

因此可以这样描述：

> 文本切分优先保留段落和句子边界；如果某个文本块超过 chunk_size，会递归尝试更细粒度的分隔符继续切分；最后再把小片段合并成接近 800 字符的 chunk，并通过 overlap 保留上下文连续性。

---

## 6. Chunk Metadata 设计

每个 chunk 写入 Qdrant 时，不只保存向量，还会保存 payload。

代码：

```python
payload={
    "content": chunk,
    "source": file_path.name,
    "category": category,
    "subcategory": subcategory,
    "chunk_index": i,
    "total_chunks": len(chunks),
    "content_hash": hashlib.md5(chunk.encode()).hexdigest(),
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `content` | chunk 原文 |
| `source` | 来源文件名 |
| `category` | 大类，例如 health / medication / tcm |
| `subcategory` | 子类，一般是文件 stem |
| `chunk_index` | 当前 chunk 在文档中的序号 |
| `total_chunks` | 当前文档总 chunk 数 |
| `content_hash` | chunk 内容 hash，用于追踪或去重 |

point id 生成方式：

```python
point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{file_path}:{i}"))
```

也就是根据：

```text
文件路径 + chunk 序号
```

生成稳定 UUID。

---

## 7. Embedding 模型与调用方式

配置位置：

```text
app/config.py
```

当前 embedding 配置：

```python
embedding_provider: str = "dashscope"
embedding_model: str = "text-embedding-v4"
dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
```

调用位置：

```text
app/llm/router.py
```

核心逻辑：

```python
_model = model or f"openai/{settings.embedding_model}"
```

所以实际通过 LiteLLM 调用的模型名类似：

```text
openai/text-embedding-v4
```

provider 选择逻辑：

```python
provider_map = {
    "glm": (settings.glm_api_key, settings.glm_base_url),
    "openai": (settings.openai_api_key, None),
    "deepseek": (settings.deepseek_api_key, settings.deepseek_base_url),
    "dashscope": (settings.dashscope_api_key, settings.dashscope_base_url),
}
```

因为当前配置是：

```python
embedding_provider = "dashscope"
```

所以实际调用的是：

```text
DashScope compatible-mode
模型：text-embedding-v4
base_url：https://dashscope.aliyuncs.com/compatible-mode/v1
```

向量维度：

```text
1024
```

---

## 8. Embedding Batch 策略

代码位置：

```text
app/llm/router.py
```

配置：

```python
MAX_EMBED_BATCH = 10
```

代码逻辑：

```python
for i in range(0, len(texts), self.MAX_EMBED_BATCH):
    batch = texts[i:i + self.MAX_EMBED_BATCH]
```

也就是说，embedding 不是一次把全部 chunks 丢给模型，而是每批最多 10 条。

这样做的原因：

- 避免 embedding provider 的批量限制；
- 降低单次请求超时概率；
- 便于失败定位。

---

## 9. Qdrant Collection 创建

当前部署版本使用 Qdrant 服务模式。

配置中：

```text
qdrant_url=http://localhost:6333
```

所以虽然 `demo_mode=True`，但由于设置了 `qdrant_url`，实际走的是：

```text
app/rag/engine_qdrant.py
```

而不是 local engine。

collection 创建代码：

```python
await self.client.create_collection(
    collection_name=name,
    vectors_config={
        "dense": models.VectorParams(
            size=1024,
            distance=models.Distance.COSINE,
        )
    },
    sparse_vectors_config={
        "sparse": models.SparseVectorParams()
    },
)
```

因此 Qdrant 配置是：

```text
dense vector: 1024 维，Cosine 相似度
sparse vector: Qdrant sparse vector index
collection schema: named vectors，字段名为 dense / sparse
```

注意：从纯 dense vector 升级到 named dense+sparse 后，需要重建知识库 collection 并重新入库：

```bash
python scripts/ingest_knowledge.py --recreate
```

---

## 10. 入库完整流程

入库函数：

```text
app/rag/ingest.py -> ingest_file()
```

完整流程：

```text
读取文件
  → 判断后缀是否支持
  → 加载文本
  → RecursiveCharacterTextSplitter 切分
  → router.embed(chunks) 生成 dense embedding
  → encode_sparse_text(chunk) 生成 lexical sparse vector
  → 构造 Qdrant PointStruct，vector 同时包含 dense / sparse
  → upsert 到对应 collection
```

核心代码片段：

```python
text = LOADERS[suffix](file_path)

splitter = RecursiveCharacterTextSplitter(
    chunk_size=settings.rag_chunk_size,
    chunk_overlap=settings.rag_chunk_overlap,
    separators=["\n\n", "\n", "。", "；", "，", " ", ""],
)
chunks = splitter.split_text(text)

router = get_llm_router()
embeddings = await router.embed(chunks)

points.append(
    models.PointStruct(
        id=point_id,
        vector={
            "dense": embedding,
            "sparse": encode_sparse_text(chunk),
        },
        payload={...},
    )
)

await engine.client.upsert(
    collection_name=collection_name,
    points=points,
)
```

---

## 11. 在线查询：Query 改写与 Hybrid 向量化

代码位置：

```text
app/rag/engine_qdrant.py
```

当前检索前会先做 query rewrite。配置项位于：

```text
app/config.py
```

```python
rag_query_rewrite_enabled: bool = True
```

核心逻辑：

```python
retrieval_query = await self._rewrite_query_for_retrieval(query)
router = get_llm_router()
q_embedding = (await router.embed([retrieval_query]))[0]
q_sparse = encode_sparse_text(retrieval_query)
```

也就是说，用户原始问题不会直接进入检索，而是先改写成更适合检索的短 query；然后同一个 `retrieval_query` 会同时生成：

```text
1. dense query vector：用于语义召回
2. sparse query vector：用于关键词/词项召回
```

### 11.1 Query rewrite prompt

改写函数：

```python
async def _rewrite_query_for_retrieval(self, query: str) -> str:
    if not self.query_rewrite_enabled:
        return query
    ...
```

Prompt 要求：

```text
你是健康知识库检索查询改写器。
请把用户口语化问题改写成适合向量检索的中文关键词短句。
保留疾病、症状、药物、饮食、运动、检查指标等核心医学概念；
不要回答问题，不要添加用户未提到的诊断结论；
只输出一行检索 query，最多 40 个中文字符。
```

例如：

```text
原始 query：我血压有点高，吃东西要注意啥？
改写后 query：高血压 低盐饮食 钠摄入 控制 建议
```

这样做的原因：

- 用户问题往往比较口语化，直接向量化可能召回不稳定；
- 改写后保留核心医学概念，有利于匹配知识库 chunk；
- 控制输出长度，避免 query 被扩展得太散；
- 如果改写失败，会自动 fallback 到原始 query。

Fallback 逻辑：

```python
except Exception as e:
    log.warning("rag_query_rewrite_failed", error=str(e))
return query
```

### 11.2 Query dense + sparse encoding

改写后的 `retrieval_query` 会分成两路：

```text
Dense：DashScope text-embedding-v4 → 1024 维语义向量
Sparse：app/rag/sparse.py -> encode_sparse_text() → Qdrant SparseVector
```

也就是：

```text
用户原始问题
  → LLM query rewrite
  → retrieval_query
  ├─→ DashScope text-embedding-v4 → dense query vector
  └─→ lexical sparse encoder       → sparse query vector
```

`sparse.py` 的实现是无额外依赖的轻量词项编码：

```text
英文/数字：按完整 token lower-case 进入 sparse vector
中文：按单字 unigram + 相邻 bigram 进入 sparse vector
权重：log-scaled term frequency + L2 normalize
index：对 token 做稳定 hash，映射到固定 sparse bucket
```

这样可以补足纯 dense retrieval 对药名、疾病名、检查指标等精确词项不够敏感的问题。

注意：rerank 阶段仍使用用户原始 query，这样可以让最终相关性判断贴近用户真实问题。

---

## 12. 在线召回：Qdrant 原生 Hybrid Search

检索函数：

```text
app/rag/engine_qdrant.py -> retrieve()
```

首先确定要检索哪些 collection：

```python
target_collections = [
    COLLECTIONS[c] for c in (collections or COLLECTIONS.keys())
    if c in COLLECTIONS
]
```

如果指定：

```python
collections=["health"]
```

则只检索：

```text
health_knowledge
```

如果不指定 collection，则检索全部：

```text
health_knowledge
medication_info
tcm_wellness
```

Qdrant Hybrid 检索代码：

```python
response = await self.client.query_points(
    collection_name=coll_name,
    prefetch=[
        models.Prefetch(
            query=q_embedding,
            using="dense",
            limit=self.rerank_top_k,
        ),
        models.Prefetch(
            query=q_sparse,
            using="sparse",
            limit=self.rerank_top_k,
        ),
    ],
    query=models.FusionQuery(fusion=models.Fusion.RRF),
    limit=self.rerank_top_k,
    with_payload=True,
)
```

当前配置：

```python
rag_rerank_top_k = 20
```

也就是每次召回候选上限为 20。

召回方式：

```text
retrieval_query
  ├─→ dense query vector  → Qdrant dense prefetch，语义召回
  └─→ sparse query vector → Qdrant sparse prefetch，关键词/词项召回
       ↓
    Qdrant Fusion.RRF
       ↓
    返回 hybrid fused chunks
```

RRF（Reciprocal Rank Fusion）的作用是融合两路召回排名：

```text
Dense 路更擅长语义相似：比如“血压高吃什么”匹配“高血压饮食管理”
Sparse 路更擅长精确词项：比如“二甲双胍”“LDL-C”“尿酸”等药名/指标名
```

---

## 13. 多 Collection 结果合并

每个 Qdrant hit 会转成统一结构：

```python
{
    "content": payload.get("content", ""),
    "source": payload.get("source", "unknown"),
    "category": payload.get("category", ""),
    "score": hit.score,
    "collection": coll_name,
}
```

然后放入：

```python
all_results
```

多 collection 合并后先按 Qdrant hybrid fusion score 排序：

```python
all_results.sort(key=lambda x: x["score"], reverse=True)
candidates = all_results[:self.rerank_top_k]
```

也就是说：

```text
多 collection 召回结果
  → 合并
  → 按 Qdrant score 降序排序
  → 取前 20 条进入 rerank
```

---

## 14. Rerank 模型与逻辑

Rerank 代码位置：

```text
app/rag/engine_qdrant.py -> _rerank()
```

调用地址：

```text
https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank
```

模型：

```text
gte-rerank
```

请求体：

```python
json={
    "model": "gte-rerank",
    "input": {
        "query": query,
        "documents": documents,
    },
    "parameters": {
        "top_n": min(top_n, len(documents)),
        "return_documents": True,
    },
}
```

其中：

```python
documents = [d.get("content", "") for d in docs]
```

也就是把候选 chunk 文本传给 rerank 模型。

rerank 之后，用 DashScope 返回的相关性分数替换原来的向量相似度分数：

```python
"score": item.get("relevance_score", 0.0)
```

---

## 15. 最终返回 top_k

配置位置：

```text
app/config.py
```

当前配置：

```python
rag_top_k: int = 5
rag_rerank_top_k: int = 20
```

也就是：

```text
候选召回 / rerank candidates：20
最终返回：5
```

代码：

```python
return candidates[:top_k]
```

如果 DashScope API Key 存在，并且候选数大于 top_k，则启用 rerank：

```python
if self.dashscope_api_key and len(candidates) > top_k:
    try:
        candidates = await self._rerank(query, candidates, top_k)
    except Exception:
        log.exception("rerank_failed")
```

如果 rerank 失败，则 fallback 到 Qdrant 向量相似度排序结果。

---

## 16. Agent 如何调用 RAG

Agent 不直接操作 Qdrant，而是通过工具和服务层调用。

服务层：

```text
app/services/knowledge_service.py
```

提供：

```python
search_health(query)
search_medication(query)
search_tcm(query)
search_all(query)
```

对应关系：

| 方法 | 检索范围 |
|---|---|
| `search_health` | `health_knowledge` |
| `search_medication` | `medication_info` |
| `search_tcm` | `tcm_wellness` |
| `search_all` | 全部 collection |

工具层：

```text
app/agent/tools/knowledge.py
```

例如：

```python
async def search_health(query: str) -> str:
    results = await KnowledgeService.search_health(query)
```

然后格式化为文本返回给 Agent：

```python
formatted = "\n".join(
    f"- {r.get('content', str(r))}" for r in results
)
return f"Health knowledge for \"{query}\":\n{formatted}"
```

整体调用路径：

```text
Agent
  → search_health / search_medication / search_tcm 工具
  → KnowledgeService
  → RAGEngine.retrieve()
  → Qdrant 检索
  → DashScope gte-rerank
  → 返回 top_k chunk
  → Agent 基于检索结果回答
```

---

## 17. TCM 检索的特殊 fallback

代码位置：

```text
app/agent/tools/knowledge.py
```

`search_tcm` 中有一个特殊逻辑：

如果 tcm collection 结果为空，或者少于 2 条：

```python
if not results or len(results) < 2:
    health_results = await KnowledgeService.search_health(query)
```

会额外检索 health collection。

然后合并去重：

```python
seen = {r.get('content', str(r)) for r in results}
for hr in health_results:
    if hr.get('content', str(hr)) not in seen:
        results.append(hr)
```

再按 score 排序取前 5：

```python
results = sorted(
    results,
    key=lambda r: r.get('score', r.get('relevance_score', 0.0)),
    reverse=True,
)[:5]
```

可以这样解释：

> 对中医养生类问题，如果 tcm collection 召回不足，会 fallback 到 health collection 做补充召回，提高回答覆盖率。

---

## 18. 引用来源处理

代码位置：

```text
app/rag/engine_qdrant.py -> retrieve_with_refs()
```

该方法返回：

```python
context_string, refs
```

其中 refs 会对 source 做去重：

```python
seen_sources: set[str] = set()

if source and source not in seen_sources:
    seen_sources.add(source)
    refs.append({
        "index": i,
        "source": source,
        "collection": r["collection"],
        "score": round(r["score"], 3),
    })
```

因此前端展示引用资料时，同一个来源文件不会重复展示太多次。

---

## 19. 当前实际运行模式说明

项目里有两个 engine：

```text
app/rag/engine_qdrant.py
app/rag/engine_local.py
```

`engine_local.py` 中 collection 维度写的是：

```python
size=1536
```

但当前实际 Qdrant collection 是：

```text
size=1024
```

并且当前配置中：

```text
qdrant_url=http://localhost:6333
```

所以当前部署版本实际使用的是：

```text
app/rag/engine_qdrant.py
```

不是 local engine。

面试时可以说：

> 当前部署版本使用 Qdrant 服务模式，collection 向量维度是 1024，对应 DashScope text-embedding-v4。

---

## 20. 面试回答版本

如果面试官问：

> 讲一下你这个 RAG 系统具体怎么做的？

可以这样回答：

> 我项目里的 RAG 入库逻辑在 `app/rag/ingest.py`。文档支持 md、txt 和 pdf，md/txt 直接读取，pdf 用 pypdf 抽取文本。切分使用 LangChain 的 `RecursiveCharacterTextSplitter`，`chunk_size=800`，`chunk_overlap=200`，separators 是段落、换行、中文句号、分号、逗号、空格和字符级兜底，所以不是硬切，而是尽量保留语义边界。
>
> 向量化通过 `app/llm/router.py` 里的 `embed` 方法调用 LiteLLM，当前 embedding provider 是 DashScope，模型是 `text-embedding-v4`，每批最多 10 条。向量写入 Qdrant，collection 分成 `health_knowledge`、`medication_info`、`tcm_wellness`，维度 1024，距离函数是 Cosine。每个 point 的 payload 保存 chunk 内容、来源文件、category、subcategory、chunk_index 和 content_hash。
>
> 查询时，用户 query 先用同一个 embedding 模型向量化，然后在 Qdrant 里用 `query_points` 做向量相似度检索。系统会按 collection 搜索，合并结果后根据 score 排序，先取 `rag_rerank_top_k=20` 条候选，再调用 DashScope 的 `gte-rerank` 做重排，最终返回 `rag_top_k=5` 条给 Agent 工具使用。这样可以先用向量召回保证覆盖，再用 rerank 提升相关性。

---

## 21. 可优化点

当前实现主要是：

```text
Dense Vector Retrieval + Rerank
```

已经可以满足 Demo 场景。

后续可以优化：

1. 加 BM25，做 hybrid retrieval；
2. 做 query rewrite，提高召回覆盖率；
3. 给 chunk 拼接标题路径，增强上下文；
4. 对 PDF 抽取文本做更细清洗；
5. 根据 category / source 做更细粒度过滤；
6. 对 chunk 结果做 MMR 去冗余；
7. 增加召回评测集，评估 top_k 命中率和 rerank 效果。

---

## 22. 最终链路图

```text
                ┌──────────────────────────┐
                │ data/knowledge 文档资料   │
                │ md / txt / pdf            │
                └─────────────┬────────────┘
                              │
                              ▼
                ┌──────────────────────────┐
                │ 文档加载                  │
                │ md/txt: read_text         │
                │ pdf: pypdf.extract_text   │
                └─────────────┬────────────┘
                              │
                              ▼
                ┌──────────────────────────┐
                │ 文本切分                  │
                │ RecursiveCharacterSplitter│
                │ size=800 overlap=200      │
                └─────────────┬────────────┘
                              │
                              ▼
                ┌──────────────────────────┐
                │ Embedding                 │
                │ DashScope text-embedding-v4│
                │ 1024维，batch=10          │
                └─────────────┬────────────┘
                              │
                              ▼
                ┌──────────────────────────┐
                │ Qdrant                    │
                │ health / medication / tcm │
                │ Cosine similarity         │
                └─────────────┬────────────┘
                              │
用户问题 ──query embedding─────┘
                              │
                              ▼
                ┌──────────────────────────┐
                │ 向量召回                  │
                │ query_points, top 20      │
                └─────────────┬────────────┘
                              │
                              ▼
                ┌──────────────────────────┐
                │ Rerank                    │
                │ DashScope gte-rerank      │
                └─────────────┬────────────┘
                              │
                              ▼
                ┌──────────────────────────┐
                │ 返回 top 5 chunks         │
                │ 给 Agent 工具 / LLM       │
                └──────────────────────────┘
```
