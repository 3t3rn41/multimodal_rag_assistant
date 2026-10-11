# 基于多模态 RAG 的智能问答助手

一个面向文档、图片、音频和视频资料的多模态检索增强生成（RAG）系统。项目目标是将非结构化资料统一解析为带有来源、页码或时间轴信息的 Chunk，通过混合检索与重排序召回可靠上下文，再由大模型生成可追溯的流式回答。

> 当前状态：成员 A 已实现 Vue 3 前端、FastAPI 后端、Celery 文档任务及开发/部署入口，并接入 B 的数据处理和 C 的 RAG 模块。网页链路当前支持 PDF、DOCX、TXT、MD 的上传、异步入库、流式问答与引用查看；图片和音视频能力已有数据/算法边界，网页接入与全链路运行验收仍待完成。

## 项目目标

系统围绕以下链路构建，当前网页已接通文档流程：

```text
文件上传 → 解析/抽取 → 清洗与切片 → 多模态向量化 → 向量库入库
    → 混合检索 → Rerank 重排 → 大模型生成 → 流式回答与引用溯源
```

当前已实现：

- 邮箱验证码注册、登录和密码重置，以及用户数据隔离；
- 知识库管理，PDF、DOCX、TXT、MD 上传和 arXiv/PDF 链接导入；
- Celery 异步解析、切片和向量入库，任务进度轮询与失败后重新解析；
- 向量检索与 BM25 加权 RRF 融合，并通过 Jina Rerank 重排；
- SSE 流式回答、Markdown 渲染、会话历史、回答中断与导出；
- 可信引用、文档页码/原文定位，检索无依据时明确拒答。

后续将接入图片和音视频上传、媒体引用播放、扫描文档 OCR、大文件分片上传及任务 WebSocket 推送。

## 系统架构

### 主要模块

| 模块 | 主要职责 | 当前实现 |
| --- | --- | --- |
| 前端与交互 | 登录、知识库管理、文件上传、解析进度、对话与引用查看 | Vue 3、Vite、Pinia、Vue Router、JavaScript/TypeScript |
| 后端 API | 用户、文件、知识库、任务、对话和 Chunk 溯源接口 | FastAPI、分层架构、SSE |
| 异步任务 | 文档解析、向量化、重试和资源清理 | Celery + Redis |
| 数据处理 | 文档解析、清洗、切片；图片/音视频适配边界 | `ingestion/`、PyMuPDF、DOCX 解析器；媒体模块提供 FFmpeg/ASR/VLM 适配 |
| 向量与检索 | API 多模态 Embedding、向量入库、向量检索、BM25、RRF | Qdrant、Jina Embeddings API、`rag_engine/` |
| 生成与评估 | Rerank、Prompt、流式生成、引用校验、效果评估 | Jina Reranker、OpenAI-compatible 模型 API |
| 基础设施 | 关系数据、迁移、对象存储、服务编排与部署 | MySQL、SQLAlchemy/Alembic、MinIO、Docker Compose |

### 数据流与异步任务

上传接口保存原文件到 MinIO、写入 MySQL 并返回文档及任务信息。Celery 在
`mmrag.documents` 队列中执行解析、切片、Embedding 和 Qdrant 入库；队列前缀可由
`CELERY_QUEUE_PREFIX` 配置。当前资源清理任务也使用该队列，媒体任务拆分留待后续接入。

统一任务状态机为：

```text
PENDING → PROCESSING → SUCCESS
                    ↘ FAILED（可重试）
```

处理中通过 `sub_status` 报告 `PARSING`、`SLICING`、`EMBEDDING` 和 `INDEXING`，
前端轮询获取进度、失败阶段及重试次数。临时故障有限重试，终止失败后可重新解析。

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

## 主要 API

| 能力 | 接口 | 说明 |
| --- | --- | --- |
| 用户认证 | `POST /api/auth/register`、`POST /api/auth/verify-registration`、`POST /api/auth/login` | 邮箱验证码注册与登录 |
| 文件上传 | `POST /api/files/upload`、`POST /api/files/upload_url` | 普通文件上传或 arXiv/PDF 链接导入，返回文档及任务信息 |
| 知识库管理 | `GET/POST /api/knowledge`、`GET/PATCH/DELETE /api/knowledge/{kb_id}` | 知识库列表、详情、修改与删除 |
| 知识库文件 | `GET/POST /api/knowledge/{kb_id}/files` | 查询文件或关联已上传文件 |
| 任务状态 | `GET /api/tasks/{id}`、`GET /api/files/{doc_id}/status` | 轮询解析进度与失败原因 |
| 重新解析 | `POST /api/files/{doc_id}/reparse` | 创建新一轮解析任务 |
| 对话问答 | `POST /api/chat` | 发起支持 SSE 流式返回的对话 |
| 历史记录 | `GET /api/chat/history`、`GET /api/chat/sessions/{session_id}/messages` | 查询会话和消息历史 |
| 引用溯源 | `GET /api/chunks/{id}`、`GET /api/chunks/{id}/source` | 获取可信 Chunk、来源正文与定位信息 |

网页 SSE 使用 `start`、`stage`、`answer_chunk`、`citation`、`done`、`aborted` 和
`error` 事件，由后端转换 C 的内部事件。完整接口以 FastAPI `/docs` 为准。

## 角色与交付物

| 负责人 | 角色 | 主要交付物 |
| --- | --- | --- |
| 成员 A | 全栈工程师 | Vue 前端、FastAPI 后端、Celery 任务、MySQL 迁移、开发脚本、Docker Compose、全链路联调 |
| 成员 B | 多模态数据工程师 | 文档/媒体解析、对齐融合、切片与元数据规范、Embedding 入库、质量样例集 |
| 成员 C | AI 与 RAG 算法工程师 | 混合检索、Rerank、Prompt 模板、大模型适配、引用输出、评估脚本与报告 |

协作以统一 Chunk、任务状态、向量库 payload 和对象存储路径为边界；A 负责应用层接入、权限隔离及持久化，B/C 负责数据处理和算法实现。

## 基础设施与快速启动

`compose.yaml` 已提供完整应用与基础设施编排：

```text
frontend · backend · worker · bootstrap · mysql57 · redis · minio · qdrant
```

MySQL 保存用户、文件、知识库、任务、会话、消息和 Chunk 元数据；MinIO 的
`raw-files` 桶保存原始文件，Qdrant 保存向量及 Chunk payload。
`bootstrap` 负责 Alembic 迁移和存储桶初始化。

**Windows本地开发**需要 Docker Desktop、Python 3.11+ 的 Conda 环境（默认名为 `rag`）和
Node.js 20.19+ 或 22.12+。首次安装与配置：

```powershell
conda activate rag
python -m pip install -e '.[app]'
Set-Location frontend
npm.cmd ci
Set-Location ..
.\start-dev.ps1 -CheckOnly
.\start-dev.ps1
```

已有 `.env` 时保留原配置。启动前填写 Jina 和问答模型密钥、MySQL/MinIO 凭据、
SMTP 发信配置及应用地址；最小配置见 [`docs/member-a-fullstack.md`](./docs/member-a-fullstack.md)。
然后在项目根目录运行：

```powershell
.\start-dev.ps1 -CheckOnly
.\start-dev.ps1
```

脚本启动四个基础设施容器及本地 API、Vite、Worker。默认前端地址为
`http://127.0.0.1:5174`，API 文档为 `http://127.0.0.1:8001/docs`。

**完整容器部署**使用：

```powershell
.\start-dev.ps1 -StopApps
docker compose up -d --build
docker compose ps --all
```

从本地开发切换时先执行
`.\start-dev.ps1 -StopApps`，避免端口冲突。

## 开发里程碑

1. **M1：契约冻结** —— 确定 Chunk 格式、任务状态机、向量库和集合设计。
2. **M2：最小闭环** —— 文档上传、解析入库、检索问答和前端展示已接入，待真实环境验收。
3. **M3：多模态能力** —— 数据适配边界已提供，继续接入图片/音视频网页流程与播放。
4. **M4：质量优化** —— 混合检索、Rerank 和评估基线已实现，继续补充真实语料回归。
5. **M5：部署交付** —— 已提供 Docker Compose 与开发脚本，待目标环境全链路验收。

## 评估指标

项目将覆盖检索准确率（Precision）、召回率（Recall）、命中率（Hit Rate）、回答忠实度（Faithfulness）和引用准确率等指标。评估集计划覆盖文本、图片、视频及混合问题，并记录标准答案与期望引用来源。

## 成员 A 全栈模块

成员 A 的实现位于 `backend/` 和 `frontend/`：

- Vue 3 工作台提供认证、知识库、上传进度、对话历史和引用原文查看；
- FastAPI 按认证、文件、知识库、任务、对话和模型状态划分业务模块；
- Celery 接入 B 的解析与入库能力，应用层接入 C 的混合检索、重排及流式生成；
- SQLAlchemy/Alembic、MinIO 和 Qdrant 分别管理关系数据、原始文件和向量；
- `start-dev.ps1` 与 `compose.yaml` 提供本地开发和完整容器部署入口。

接入边界、配置示例和当前限制见 [`docs/member-a-fullstack.md`](./docs/member-a-fullstack.md)。

## 成员 C 算法模块

成员 C 的第一版实现位于 `rag_engine/`，包括：

- BM25 + 向量检索 + 加权 RRF 混合召回；
- Qdrant `query_points` 适配器；
- Jina `jina-reranker-v3` API Rerank 适配器；
- OpenAI-compatible 多厂商流式模型适配；
- 可信 Chunk 白名单校验与结构化引用；
- 评估数据集、Precision/Recall/Hit Rate/MRR/Citation Accuracy 指标和回归脚本。

详细接入说明见 [`docs/member-c-rag.md`](./docs/member-c-rag.md)，基础测试可运行：

```bash
python -m unittest discover -s tests -v
```

成员 B 的数据解析、切片、时间对齐与向量入库接入说明见
[`docs/member-b-data.md`](./docs/member-b-data.md)。

成员 B 的向量化实现是 API-only：不会在本地下载或加载 Embedding 模型，默认使用
Jina `jina-embeddings-v5-omni-small`。复制
[`.env.example`](./.env.example) 并填写 `RAG_EMBEDDING_API_URL`、
`JINA_API_KEY`、模型名和可选维度后，可用
`python -m scripts.index_chunks --rebuild` 会在 Jina 专用的
`jina_v5_omni_small_1024` 集合中全量重建索引；普通运行支持断点续传并按持久化
UUID 跳过已入库数据。
模型比较和输入路由规则见
[`docs/embedding-model-selection.md`](./docs/embedding-model-selection.md)。

## 成员 B 数据模块

成员 B 的实现位于 `ingestion/`，与成员 C 的 `rag_engine` 通过统一的
`rag_engine.models.Chunk` 对接：

- `chunk_document`：保留页码、标题层级，并按重叠窗口切分文档块；
- `image_chunk`：将图片描述和原图路径封装为可检索 Chunk；
- `chunk_media`：按时间窗融合 ASR 文本和视频帧描述；转写只归属一个窗口，引用时间使用实际证据边界；
- `ApiMultimodalEmbedder`：通过 Jina v5-omni Embedding API 统一处理文本、图片、原始音频、原始视频和代表帧；
- `index_chunks`：批量校验向量、支持断点续传，并通过 `QdrantVectorWriter` 写入向量库；
  已有集合会校验维度和 named vector，临时 Qdrant/转写故障会有限重试。

Embedding 请求显式使用 `normalized=true` 和 `embedding_type=float`，网络错误及
429/5xx 等临时错误会按指数退避重试。媒体流水线会先按 Chunk 的时间范围裁剪音频/视频；
生产环境需在上传 MinIO 后将裁剪文件映射为 `minio://` 或 presigned HTTP(S) URL，
否则索引命令会直接拒绝本地路径，避免退化为纯文本向量。

切片时会为每个 Chunk 生成并持久化随机 UUID4 到
`extra["qdrant_point_id"]`；Qdrant 断点索引只接受该 UUID，不会从业务 ID 计算哈希。

这些接口不强绑定具体 PDF/OCR/ASR/VLM 服务，上游解析器只需产出
`DocumentBlock`、`TranscriptSegment` 和 `FrameDescription` 即可接入。生成的
Chunk 可直接被 C 的 BM25/混合检索和 `QdrantVectorRetriever` 消费。

## 文档

- [项目分工详细说明书](./项目分工详细说明书.md)：角色职责、接口边界、技术选型和交付物的完整说明。
- [成员 A：全栈实现与接入](./docs/member-a-fullstack.md)：前后端、任务、配置与启动方式。
- [成员 B：数据处理](./docs/member-b-data.md)：解析、切片、媒体对齐和向量入库。
- [成员 C：RAG 算法](./docs/member-c-rag.md)：检索、重排、生成、引用和评估。
- [Embedding 模型选型](./docs/embedding-model-selection.md)：Jina 模型与输入路由约定。
