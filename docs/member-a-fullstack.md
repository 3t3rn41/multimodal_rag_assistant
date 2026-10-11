# 成员 A：全栈实现与接入

成员 A 的实现位于 `backend/` 和 `frontend/`，负责把 B 的数据处理和 C 的
RAG 算法接入可操作的网页，并管理权限、任务、持久化和部署入口。
当前网页支持 PDF、DOCX、TXT、MD 文档链路，多模态网页接入仍待完善。

## 实现概览

- 前端：Vue 3、Vite、Pinia 和 Vue Router，包含邮箱验证码注册/登录、密码重置、
  知识库管理、文件上传、解析进度、流式对话、历史记录和引用原文查看。
- 后端：FastAPI，按 `auth`、`upload`、`knowledge`、`task`、`chat` 等业务模块
  分层；模型状态页面只读，模型地址、名称和密钥由服务端 `.env` 提供。
- 存储：MySQL 保存关系数据和 Chunk 元数据，MinIO 保存原文件，Qdrant 保存向量；
  SQLAlchemy/Alembic 负责数据访问及数据库迁移。
- 任务：Celery + Redis 执行文档解析、切片、向量化和资源清理，支持临时故障重试。

## 协作边界

### 接入成员 B

上传接口先将原文件写入 MinIO，并创建文档与任务记录。Worker 调用 `ingestion/`
的文档解析入口和 `chunk_document`，随后调用 `ApiMultimodalEmbedder`、
`index_chunks` 与 `QdrantVectorWriter`，统一产出 `rag_engine.models.Chunk`。
A 持久化 Chunk payload、来源定位和 `extra["qdrant_point_id"]`，保留 B 生成的 UUID。

默认队列为 `mmrag.documents`，前缀由 `CELERY_QUEUE_PREFIX` 控制。任务状态为
`PENDING → PROCESSING → SUCCESS/FAILED`；处理阶段通过 `sub_status` 暴露
`PARSING`、`SLICING`、`EMBEDDING`、`INDEXING`，前端轮询进度和失败原因。

### 接入成员 C

应用层先按当前用户、所选知识库和文件启用状态确定可检索 Chunk，再组装 C 的
`BM25Retriever`、`QdrantVectorRetriever`、`HybridRetriever`、`JinaReranker`
和 `RAGPipeline`。向量查询使用允许的 Chunk ID 过滤，返回结果也校验同一范围。

C 的内部事件由后端转换为网页 SSE：`text` 对应 `answer_chunk`，`citations`
对应逐条 `citation`；另外提供 `start`、`stage`、`done`、`aborted`、`error`。
回答、可信引用及过程记录写入会话历史，引用页码和路径来自可信 Chunk 元数据。

应用使用约定的 Jina Embedding/Rerank 模型、1024 维、`dense` named vector 和
`jina_v5_omni_small_1024` 集合。数据与算法细节分别见
[`member-b-data.md`](./member-b-data.md) 和 [`member-c-rag.md`](./member-c-rag.md)。

## 主要接口

业务接口统一使用 `/api` 前缀；文件、知识库和问答等接口校验登录状态及资源归属。
完整定义见 FastAPI `/docs`。

| 能力 | 接口 | 说明 |
| --- | --- | --- |
| 用户认证 | `POST /api/auth/register`、`POST /api/auth/verify-registration`、`POST /api/auth/login` | 邮箱验证码注册与登录 |
| 知识库 | `GET/POST /api/knowledge`、`GET/PATCH/DELETE /api/knowledge/{kb_id}` | 列表、创建、详情、修改与删除 |
| 知识库文件 | `GET/POST /api/knowledge/{kb_id}/files` | 查询文件或关联已上传文件 |
| 文件上传 | `POST /api/files/upload`、`POST /api/files/upload_url` | 普通文件上传或 arXiv/PDF 链接导入 |
| 任务进度 | `GET /api/tasks/{id}`、`GET /api/files/{doc_id}/status` | 进度、失败阶段和重试信息 |
| 重新解析 | `POST /api/files/{doc_id}/reparse` | 创建新一轮解析任务 |
| 流式问答 | `POST /api/chat`、`POST /api/chat/sessions/{session_id}/abort` | SSE 回答与主动中断 |
| 会话历史 | `GET /api/chat/history`、`GET /api/chat/sessions/{session_id}/messages` | 会话和消息列表 |
| 引用溯源 | `GET /api/chunks/{id}`、`GET /api/chunks/{id}/source` | 可信原文、来源正文及定位信息 |
| 模型状态 | `GET /api/users/me/models` | 只读配置状态，不返回密钥 |

## 快速启动

### 配置与依赖

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

`.env.example` 已包含 Jina 和 Qdrant 配置，还需在本地 `.env` 补充应用、基础设施、
SMTP 和问答模型设置。下列为开发配置示例，占位值须替换为实际值：

```dotenv
APP_ENV=development
APP_BACKEND_URL=http://127.0.0.1:8001
PUBLIC_BASE_URL=http://127.0.0.1:5174
APP_CORS_ORIGINS=http://localhost:5174,http://127.0.0.1:5174
SECRET_KEY=replace_me
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3308
MYSQL_DATABASE=multimodal_rag_assistant
MYSQL_USER=mmrag
MYSQL_ROOT_PASSWORD=replace_me
MYSQL_PASSWORD=replace_me
REDIS_HOST=127.0.0.1
REDIS_PORT=6378
MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=mmragadmin
MINIO_SECRET_KEY=replace_me
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USER=replace_me
SMTP_PASSWORD=replace_me
SMTP_FROM=sender@example.com
JINA_API_KEY=fill_me
RAG_LLM_BASE_URL=https://your-provider.example.com/v1
RAG_LLM_MODEL=your_model
RAG_LLM_API_KEY=fill_me
```

保留模板中的 Jina 模型/维度/集合设置；本地开发使用 `RAG_QDRANT_URL=http://localhost:6333`，
并保持 `RAG_QDRANT_PATH` 为空。注册和密码重置依赖真实 SMTP 配置。
配置变更后重启后端和 Worker，密钥仅保存在本地 `.env`。

### 容器入口

**完整容器部署**使用：

```powershell
.\start-dev.ps1 -StopApps
docker compose up -d --build
docker compose ps --all
```

从本地开发切换时先执行
`.\start-dev.ps1 -StopApps`，避免端口冲突。

## 当前限制

- 网页尚未接入图片/音视频上传、媒体引用播放及扫描 PDF 的 OCR，优先使用可选中文字的 PDF。
- 上传为普通 multipart 请求，当前上限为 100 MiB；分片上传与任务 WebSocket 推送尚未实现。
- URL 导入当前支持 arXiv/PDF，普通网页正文解析待接入。
- 网页问答要求真实 Jina Embedding、Rerank 和兼容模型配置，未提供网页演示模型回退。
- 启动入口和集成代码已提供，仍需使用真实文档在目标环境完成运行验收。
