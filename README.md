# 基于多模态 RAG 的智能问答助手

一个面向文档、图片、音频和视频资料的多模态检索增强生成（RAG）系统方案。项目目标是将非结构化资料统一解析为带有来源、页码或时间轴信息的 Chunk，通过混合检索与重排序召回可靠上下文，再由大模型生成可追溯的流式回答。

> 当前状态：项目处于方案落地阶段。成员 B 已完成统一 Chunk 数据契约、文档/图片/音视频切片对齐和批量向量入库边界；成员 C 的检索、重排、流式生成、结构化引用和评估基线已实现，后端 API、前端和部署模块将按里程碑继续接入。

## 项目目标

系统将围绕以下链路构建：

```text
文件上传 → 解析/抽取 → 清洗与切片 → 多模态向量化 → 向量库入库
    → 混合检索 → Rerank 重排 → 大模型生成 → 流式回答与引用溯源
```

核心体验包括：

- 支持 PDF、Word、图片、音频和视频等资料；
- 支持大文件分片上传、异步解析和任务进度展示；
- 支持文本、图片描述、音频转写和视频时间轴切片的统一检索；
- 支持向量检索与 BM25 关键词检索融合，并通过 Rerank 提升相关性；
- 支持 SSE 流式回答、Markdown 渲染和多模态引用展示；
- 引用可回溯到文档页码、图片或视频的具体时间区间，检索无依据时明确拒答。

## 系统架构

### 主要模块

| 模块 | 主要职责 | 计划技术方向 |
| --- | --- | --- |
| 前端与交互 | 知识库管理、文件上传、解析进度、对话与引用播放 | React/Vite/TypeScript 或 Vue3/Vite |
| 后端 API | 用户、文件、知识库、任务、对话和 Chunk 溯源接口 | FastAPI、分层架构、SSE |
| 异步任务 | 文档解析、媒体处理、向量化和重试 | Celery + Redis；评估 Dramatiq/arq |
| 数据处理 | PDF/Word/图片/音视频解析、清洗、切片和多模态对齐 | `ingestion/` 契约层；可接 PyMuPDF、Unstructured、FFmpeg、Whisper、OCR |
| 向量与检索 | Embedding、向量入库、向量检索、BM25、RRF | Qdrant（优先）或 Milvus、BGE/CLIP 系列 |
| 生成与评估 | Query 改写、Rerank、Prompt、流式生成、效果评估 | bge-reranker、可配置的大模型 API |
| 基础设施 | 关系数据、对象存储、服务编排与部署 | MySQL、MinIO、Docker Compose |

### 数据流与异步任务

上传后的耗时处理不占用同步请求线程，由任务队列分流：

- `queue_document`：PDF、Word 等文档解析；
- `queue_media`：音频转写、视频抽帧和媒体处理；
- `queue_vectorize`：Embedding 生成与向量入库。

统一任务状态机为：

```text
PENDING → PROCESSING → SUCCESS
                    ↘ FAILED（可重试）
```

处理中可进一步报告 `PARSING`、`SLICING`、`EMBEDDING` 和 `INDEXING` 子状态，并将进度、失败原因和重试次数提供给前端。

## Chunk 数据契约

Chunk 是数据处理、检索算法和前端溯源之间的核心接口。各模块应围绕统一字段协作：

| 字段 | 含义 |
| --- | --- |
| `chunk_id` | 全局唯一 Chunk 标识 |
| `file_id` | 所属文件标识 |
| `source_type` | `document`、`image`、`audio` 或 `video` |
| `content` | 用于检索的文本内容 |
| `embedding` | 后续生成的向量 |
| `time_start` / `time_end` | 音频、视频的时间范围 |
| `page` | 文档页码 |
| `media_path` | 原始文件、图片或帧的对象存储路径 |
| `extra` | 关键词、标题层级等扩展 JSON |

视频 Chunk 示例：

```json
{
  "chunk_id": "c_example_001",
  "file_id": "video_001",
  "source_type": "video",
  "time_start": 80,
  "time_end": 110,
  "content": "讲师演示如何配置环境变量，屏幕显示终端命令",
  "speech_text": "接下来我们配置环境变量，输入 export PATH=...",
  "frames": ["frame_001_80.jpg", "frame_001_85.jpg"],
  "keywords": ["环境变量", "export", "配置"]
}
```

## 计划 API

| 能力 | 接口 | 说明 |
| --- | --- | --- |
| 文件上传 | `POST /api/files/upload` | 分片上传并返回任务 ID |
| 知识库管理 | `GET/POST/DELETE /api/knowledge/*` | 文件列表、详情、删除和重新解析 |
| 任务状态 | `GET /api/tasks/{id}`、`WS /api/tasks/ws` | 查询或推送解析进度 |
| 对话问答 | `POST /api/chat` | 发起支持 SSE 流式返回的对话 |
| 历史记录 | `GET /api/chat/history` | 查询会话和消息历史 |
| 引用溯源 | `GET /api/chunks/{id}` | 获取 Chunk 原文和元数据 |

SSE 事件应能够表达增量文本、引用标记、图片和视频片段等结构化内容；需要双向通信时再引入 WebSocket。

## 角色与交付物

| 负责人 | 角色 | 主要交付物 |
| --- | --- | --- |
| 成员 A | 全栈工程师 | 前端、FastAPI 后端、异步任务、MySQL 脚本、Docker Compose、全链路联调 |
| 成员 B | 多模态数据工程师 | 文档/媒体解析、对齐融合、切片与元数据规范、Embedding 入库、质量样例集 |
| 成员 C | AI 与 RAG 算法工程师 | 混合检索、Rerank、Prompt 模板、大模型适配、引用输出、评估脚本与报告 |

协作以接口和数据契约为边界：先冻结 Chunk 格式、任务状态机、向量库返回结构及对象存储路径约定，再并行开发内部实现。

## 基础设施规划

计划使用 Docker Compose 编排以下服务：

```text
frontend · backend · mysql · redis · minio · qdrant
celery-worker · celery-beat（按需启用）
```

原始文件和中间产物存放于 MinIO，建议划分以下存储桶：

- `raw-files`：原始文件；
- `extracted-frames`：视频抽帧；
- `transcripts`：音频/视频转写文本；
- `thumbnails`：封面和缩略图。

数据库将重点管理用户、文件元数据、任务、会话、消息和引用映射；向量库负责向量及可过滤的 Chunk payload。

## 开发里程碑

1. **M1：契约冻结** —— 确定 Chunk 格式、任务状态机、向量库和集合设计。
2. **M2：最小闭环** —— 完成“PDF 上传 → 解析切片 → 向量化 → 文本检索问答 → 前端展示”。
3. **M3：多模态能力** —— 接入视频/音频解析、多模态对齐和图片检索。
4. **M4：质量优化** —— 加入混合检索、Rerank、评估集和回归测试。
5. **M5：部署交付** —— Docker Compose 一键部署并完成全链路验收。

## 评估指标

项目将覆盖检索准确率（Precision）、召回率（Recall）、命中率（Hit Rate）、回答忠实度（Faithfulness）和引用准确率等指标。评估集计划覆盖文本、图片、视频及混合问题，并记录标准答案与期望引用来源。

## 成员 C 算法模块

成员 C 的第一版实现位于 `rag_engine/`，包括：

- BM25 + 向量检索 + 加权 RRF 混合召回；
- Qdrant `query_points` 适配器；
- `BAAI/bge-reranker-v2-m3` CrossEncoder Rerank 适配器；
- OpenAI-compatible 多厂商流式模型适配；
- 可信 Chunk 白名单校验与结构化引用；
- 评估数据集、Precision/Recall/Hit Rate/MRR/Citation Accuracy 指标和回归脚本。

详细接入说明见 [`docs/member-c-rag.md`](./docs/member-c-rag.md)，基础测试可运行：

```bash
python -m unittest discover -s tests -v
```

成员 B 的数据解析、切片、时间对齐与向量入库接入说明见
[`docs/member-b-data.md`](./docs/member-b-data.md)。

## 成员 B 数据模块

成员 B 的实现位于 `ingestion/`，与成员 C 的 `rag_engine` 通过统一的
`rag_engine.models.Chunk` 对接：

- `chunk_document`：保留页码、标题层级，并按重叠窗口切分文档块；
- `image_chunk`：将图片描述和原图路径封装为可检索 Chunk；
- `chunk_media`：按时间窗融合 ASR 文本和视频帧描述，保留可回溯时间段；
- `embed_and_upsert`：批量校验 embedding，并通过 `QdrantVectorWriter` 写入向量库。

这些接口不强绑定具体 PDF/OCR/ASR/VLM 服务，上游解析器只需产出
`DocumentBlock`、`TranscriptSegment` 和 `FrameDescription` 即可接入。生成的
Chunk 可直接被 C 的 BM25/混合检索和 `QdrantVectorRetriever` 消费。

## 文档

- [项目分工详细说明书](./项目分工详细说明书.md)：角色职责、接口边界、技术选型和交付物的完整说明。
