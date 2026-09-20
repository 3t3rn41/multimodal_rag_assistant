# 成员 B：数据解析、切片与向量入库

成员 B 的基础实现位于 `ingestion/`，输出直接复用成员 C 的
`rag_engine.models.Chunk`，因此不需要改动 `BM25Retriever`、`HybridRetriever`
或 `QdrantVectorRetriever`。

## 与成员 C 的契约

所有入口都返回 `Chunk`，字段对应 README 的统一数据契约：

- 文档：`source_type="document"`，使用 `page` 和 `extra["heading"]`；
- 图片：`source_type="image"`，描述写入 `content`，原图写入 `media_path`；
- 音频/视频：使用 `time_start`、`time_end`，语音和画面描述合并到 `content`；
- 向量：写入 `Chunk.embedding`，传给 Qdrant 时作为 point vector，其他元数据由
  `Chunk.to_payload()` 提供。

成员 C 的 `QdrantVectorRetriever` 从 point payload 调用
`Chunk.from_payload()`，所以入库端不得把 `chunk_id`、来源类型或时间字段藏在
无法还原的自定义结构里。

## 最小示例

```python
from ingestion import DocumentBlock, chunk_document

chunks = chunk_document(
    "manual.pdf",
    [DocumentBlock("Redis 任务队列配置", page=3, heading="任务队列")],
)
```

媒体输入由上游解析器提供带时间戳的 ASR 和帧描述：

```python
from ingestion import FrameDescription, TranscriptSegment, chunk_media

chunks = chunk_media(
    "demo.mp4",
    [TranscriptSegment(2, 9, "先打开配置文件")],
    [FrameDescription(5, "终端显示配置文件", "frames/5.jpg")],
)
```

真正的 PDF/OCR/Whisper/VLM 适配器可以独立接在这些输入类型之前；这样可在不
引入重量级依赖的情况下测试切片、对齐和 C 的检索链路。

## 向量化入库

```python
from ingestion import QdrantVectorWriter, embed_and_upsert

writer = QdrantVectorWriter(client, "chunks", vector_name="dense")
embed_and_upsert(chunks, embedding_provider, writer, batch_size=64)
```

`embedding_provider` 只需实现 `embed(texts)`，返回与输入数量一致的向量。批次
内和批次间维度不一致、空向量、非有限值都会在写入前被拒绝。
