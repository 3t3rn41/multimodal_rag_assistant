# 成员 B：数据解析、切片与向量入库

成员 B 的实现位于 `ingestion/`，输出直接复用成员 C 的
`rag_engine.models.Chunk`，因此不需要改动 `BM25Retriever`、`HybridRetriever`
或 `QdrantVectorRetriever`。Embedding 不在本地加载模型，统一调用 Jina 的
`jina-embeddings-v5-omni-small` API，示例配置见 `.env.example`，模型取舍见
[`embedding-model-selection.md`](./embedding-model-selection.md)。

## 与成员 C 的契约

所有入口都返回 `Chunk`，字段对应 README 的统一数据契约：

- 文档：`source_type="document"`，使用 `page` 和 `extra["heading"]`；
- 图片：`source_type="image"`，描述写入 `content`，原图写入 `media_path`；
- 音频/视频：使用实际证据边界的 `time_start`、`time_end`，语音和画面描述合并到 `content`；固定检索桶保存在 `extra.window_start`/`window_end`；
- 向量：写入 `Chunk.embedding`，传给 Qdrant 时作为 point vector，其他元数据由
  `Chunk.to_payload()` 提供。
- `extra["qdrant_point_id"]`：由切片入口生成并随 Chunk 持久化的随机 UUID4，供
  Qdrant 断点索引使用；禁止通过业务 ID 计算哈希 ID。

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

`PyMuPDFParser`、`DocxParser`、`FFmpegMediaExtractor`、`ApiTranscriber` 和
`ApiImageCaptioner` 已提供适配边界；PDF 解析依赖可选的 PyMuPDF，音视频依赖系统
FFmpeg，转写和图片描述依赖你填写的 API。媒体流水线会按每个 Chunk 的实际
`time_start/time_end` 生成裁剪文件，并把裁剪路径写入
`extra["source_media_path"]`；只有单帧证据没有正时长时才回退到所属检索窗口。
这样切片/对齐测试不需要下载模型，也不会把真实 Token 写入仓库。

## 向量化入库

```python
from ingestion import (
    ApiMultimodalEmbedder,
    MultimodalEmbeddingAPIConfig,
    QdrantVectorWriter,
    ensure_qdrant_collection,
    index_chunks,
)

config = MultimodalEmbeddingAPIConfig.from_env()
ensure_qdrant_collection(
    client,
    "jina_v5_omni_small_1024",
    config.dimensions or 1024,
    vector_name="dense",
)
provider = ApiMultimodalEmbedder(config)
writer = QdrantVectorWriter(client, "jina_v5_omni_small_1024", vector_name="dense")
report = index_chunks(chunks, provider, writer, batch_size=64)
```

生产路径固定使用 API provider；测试可以注入假的 transport，不需要下载模型。
批次内和批次间维度不一致、空向量、非有限值都会在写入前被拒绝，`report` 会记录
总数、跳过数、实际向量化数和写入数。

生产 API 入口是 `ApiMultimodalEmbedder`：文档发送文本，图片发送文本与图片，
音频发送转写文本与原始音频，视频发送融合文本、原始视频和可访问的代表帧；
私有 `minio://` 路径必须由应用层转换为短时 presigned HTTPS URL。Jina
`v5-omni` 支持共享向量空间中的文本、图片、音频和视频输入；请求使用
`normalized=true` 与 `embedding_type=float`。API transport 对网络错误、408、425、
429 和 5xx 使用指数退避重试。`scripts/index_chunks.py` 支持已入库 Chunk 跳过、批量写入
和结束后的一致性检查：

```bash
python -m scripts.index_chunks \
  --chunks chunks.jsonl \
  --collection jina_v5_omni_small_1024 \
  --rebuild
```

`--rebuild` 只重建指定的 Jina 专用集合：先删除并新建 1024 维 COSINE 集合，
再读取完整 JSONL、重新调用 Jina Embedding 并写入全部 Chunk，不会修改旧的通用集合。
本地 Qdrant 使用 `http://localhost:6333`；Qdrant Cloud 则将集群 URL 填入
`RAG_QDRANT_URL`，并将访问令牌填入 `RAG_QDRANT_API_KEY`。
如果不想启动 Qdrant 服务，可以使用客户端的本地持久化模式：传
`--qdrant-path ./qdrant_storage`；该模式会把集合数据保存在指定目录。

`evaluation/ingestion_samples.jsonl` 提供文档、表格、图片、音频、视频和纯画面
场景的最小质量样例，测试会校验这些样例都能产出完整 Chunk 元数据。

如果上游暂时只有这种“解析记录 JSONL”，可以先导出标准 Chunk 文件：

```bash
python -m scripts.build_ingestion_chunks \
  --input evaluation/ingestion_samples.jsonl \
  --output chunks.jsonl
```

真实数据请把 `--input` 换成上游解析结果；不要把原始 PDF/视频文件直接传给
`index_chunks.py`。只有评估样例中的占位媒体 URL 不可访问时，才可临时加
`--text-only` 做文本索引验证。
