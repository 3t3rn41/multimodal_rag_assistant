# Embedding 模型选型与 API 接入

## 结论

本项目采用 API-first：运行时不下载或加载本地 embedding 模型，统一由
`ApiMultimodalEmbedder` 调用一个能同时接受文本和图片的 embedding API。默认配置
是 Jina AI 的 `jina-clip-v2` 接口；真正的 URL、模型名、维度和 Token 都从环境变量
读取，后续可以替换为团队购买的兼容服务。

选择默认方案的原因是文本和图片必须落在同一个向量空间。`jina-clip-v2` 官方模型卡
说明它是文本/图片多模态 embedding，文本塔支持 89 种语言，输出维度可以在 64 到
1024 之间截断，并给出了 `/v1/embeddings` 的文本与图片混合请求格式。生产环境应
根据实际 API 账单、延迟、数据合规和模型许可重新验收，不能把官方模型卡的 benchmark
数字当成本项目的线上指标。

## 对比

| 方案 | 跨模态 | 中文/多语言 | 向量与部署特点 | 本项目结论 |
| --- | --- | --- | --- | --- |
| OpenAI CLIP | 文本 + 图片 | 原始方案不以中文检索为目标 | 开源代码和多种视觉骨干，但需要自己托管；官方 model card 将其定位为研究输出 | 保留为研究基线，不作为默认生产 API |
| BGE-M3 | 文本 dense/sparse/ColBERT | 100+ 语言，最长 8192 token，1024 维 | 很适合中文文本与混合词法检索，但本身不是图片编码器 | 文本-only 或独立文本集合可选；不能单独满足图文同空间 |
| Jina CLIP v2 API | 文本 + 图片 | 官方模型卡标注 89 种语言 | 64–1024 维可选；API 可直接混合 `text` 与 `image` 输入 | 默认方案，文本/图片/视频代表帧共享一个 API 向量空间 |

来源：

- [Jina CLIP v2 官方模型卡](https://huggingface.co/jinaai/jina-clip-v2)
- [BGE-M3 官方模型卡](https://huggingface.co/BAAI/bge-m3)
- [OpenAI CLIP 官方仓库与 model card](https://github.com/openai/CLIP/blob/main/model-card.md)

## Chunk 到 API 输入的规则

- `document`、`audio`：把 `content` 作为 `{"text": ...}`；音频先由转写 API 生成带时间戳文本。
- `image`：同时发送图片描述文本和 `media_path` 图片 URL，两个向量 L2 归一化后取均值，再归一化。
- `video`：发送融合后的语音/画面描述文本，以及一个代表帧 URL；时间轴仍保留在 Chunk 元数据中。
- `media_path` 为 `minio://` 时，必须由应用层回调换成短时 presigned HTTPS URL；不会把私有
  MinIO 地址直接发给第三方 API。

API 返回的所有向量必须维度一致。写入 Qdrant 前会检查数量、维度、空向量和 NaN/Inf，
中断后通过 Chunk ID 跳过已存在记录，并在批处理结束后再次做一致性校验。

## 运行配置

复制 `.env.example` 后填写 `RAG_EMBEDDING_API_KEY`。不要把真实 Token 写进仓库；
批量入库命令见 `scripts/index_chunks.py`。
