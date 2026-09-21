# 成员 C：检索、重排、生成与评估实现

本文档说明成员 C 交付物的工程实现和接入边界。代码位于 `rag_engine/`，不要求前端、FastAPI 或数据解析模块改变内部实现，只依赖统一的 `Chunk` 和检索结果接口。

## 设计取舍

### 混合召回

基础实现使用本地 BM25 作为词法召回，并通过 `QdrantVectorRetriever` 接入向量检索。两路结果在应用层用加权 RRF（Reciprocal Rank Fusion）融合：

```text
向量召回 top-N ─┐
                 ├─ weighted RRF ─> 候选 top-N ─> Jina Rerank ─> top-k 上下文
BM25 召回 top-N ┘
```

RRF 只使用排名而不直接比较不同检索器的原始分数，避免余弦相似度与 BM25 分数尺度不一致。`rank_constant`、两路权重和候选数量均可配置。规模扩大后，可以把 BM25 替换为 Elasticsearch/OpenSearch，或使用 Qdrant 的 named dense/sparse vectors 和原生 Query API，而不改变后续 Rerank 和生成接口。

### Rerank

生产默认使用 `JinaReranker` 调用 `jina-reranker-v3`，对 query-document
候选重新打分，再保留最终 top-k。`CrossEncoderReranker` 仍保留为本地兼容实现，
但不属于当前生产路径；未配置 API 时可以用 `NoOpReranker` 跑通本地闭环。生产环境建议：

- 召回 top-50～top-100，再进行一次 Jina 精排；
- 通过离线评估集调节 `top_k` 和相关性阈值；
- 将 API Key 只放在环境变量中，不写入日志；
- 对模型版本、请求延迟、API 限流和线上费用做记录；
- 图片、音频和视频的多模态内容由 Jina Embeddings 在向量召回阶段处理；Jina
  `jina-reranker-v3` 精排阶段使用 Chunk 中的转写和描述文本。

### 生成与引用

Prompt 强制模型只使用召回证据，并在结尾输出结构化引用块。`CitationParser` 会：

1. 解析模型输出的引用 JSON；
2. 将引用 ID 与实际召回 Chunk 做白名单校验；
3. 丢弃模型编造的 Chunk、页码、时间和路径；
4. 从可信 Chunk 元数据生成可点击的引用标签。

`RAGPipeline.stream_answer` 会在流式输出时隐藏机器引用块，只向前端发出 `context`、`text`、`citations` 和 `done` 事件。

## 快速接入

### 仅本地 BM25

```python
from rag_engine import BM25Retriever, HybridRetriever
from rag_engine.models import Chunk

chunks = [
    Chunk("doc_1", "manual.pdf", "document", "Redis 任务队列配置", page=3),
    Chunk("doc_2", "demo.mp4", "video", "视频演示环境变量", time_start=80, time_end=110),
]
retriever = HybridRetriever(BM25Retriever(chunks), candidate_k=50)
results = retriever.search("如何配置 Redis？", top_k=8)
```

### 接入 Qdrant

```python
from qdrant_client import QdrantClient
from rag_engine.qdrant_adapter import QdrantVectorRetriever
from rag_engine.retrieval import BM25Retriever, HybridRetriever

vector = QdrantVectorRetriever(
    QdrantClient(url="http://localhost:6333"),
    collection_name="jina_v5_omni_small_1024",
    embed_query=embedding_service.embed_query,
    vector_name="dense",
)
retriever = HybridRetriever(bm25, vector, candidate_k=50)
```

### 接入多厂商模型

`OpenAICompatibleChatModel` 只要求一个 OpenAI-compatible `/chat/completions` 地址，因此可以通过 `RAG_LLM_BASE_URL`、`RAG_LLM_MODEL` 和 `RAG_LLM_API_KEY` 切换 OpenAI、云端兼容服务或自部署网关。API Key 只从环境变量读取，不写入日志。

```python
from rag_engine.llm import OpenAICompatibleChatModel, OpenAICompatibleConfig
from rag_engine.pipeline import RAGPipeline
from rag_engine.rerank import JinaRerankConfig, JinaReranker

model = OpenAICompatibleChatModel(OpenAICompatibleConfig.from_env())
pipeline = RAGPipeline(
    retriever,
    model,
    reranker=JinaReranker(JinaRerankConfig.from_env()),
    retrieval_k=50,
    answer_k=8,
)
result = await pipeline.answer("视频中如何配置环境变量？")
```

## 评估与回归

评估集和脚本位于 `evaluation/` 与 `scripts/evaluate_rag.py`。当前样例集覆盖文档、图片、音频、视频和混合问题，但没有伪造线上指标；接入真实语料后，将服务输出转换为预测 JSONL，再计算 Precision@k、Recall@k、Hit Rate、MRR 和 Citation Accuracy。

```bash
python scripts/evaluate_rag.py \
  --predictions evaluation/predictions.jsonl \
  --k 5 \
  --output evaluation/latest-report.json
```

Faithfulness 需要人工标注或独立评审模型，不能仅由检索命中率推断；该指标应在真实回答集接入后单独评估。

## 参考的成熟方案

- [Qdrant Hybrid Queries](https://qdrant.tech/documentation/search/hybrid-queries/)：dense/sparse 多路查询与 RRF 融合；
- [Qdrant Hybrid Search with Reranking](https://qdrant.tech/documentation/tutorials-basics/reranking-hybrid-search/)：先召回再重排的多阶段检索模式；
- [Jina Embeddings](https://jina.ai/en-US/embeddings/)：文本、图片、音频和视频的共享向量空间；
- [Jina Rerank API](https://jina.ai/?model=jina-reranker-v3)：文本候选的二阶段重排序。
