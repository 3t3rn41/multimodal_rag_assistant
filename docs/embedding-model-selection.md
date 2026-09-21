# SiliconFlow Qwen 多模态 Embedding 与 Rerank

## 结论

项目运行时统一使用硅基流动 API，不下载或加载本地 Embedding/Rerank 模型：

- Embedding：`Qwen/Qwen3-VL-Embedding-8B`，请求
  `https://api.siliconflow.cn/v1/embeddings`；
- Rerank：`Qwen/Qwen3-VL-Reranker-8B`，请求
  `https://api.siliconflow.cn/v1/rerank`。

硅基流动官方 Embedding 文档明确支持文本、图片 URL/base64 和混合输入；官方当前
也明确注明 VL Embedding 暂不支持直接输入视频。因此视频先由 FFmpeg 抽取代表帧，
音频先由转写 API 变成带时间戳文本，再进入统一的 Chunk 检索链路。

## 输入路由

| Chunk 类型 | Embedding API 输入 | Rerank API 文档输入 |
| --- | --- | --- |
| `document` | `{"text": content}` | `{"text": content}` |
| `image` | 文本描述 + `{"image": media_url}`，向量归一化后取均值 | `{"image": media_url}` |
| `audio` | `{"text": content}`，内容来自带时间戳 ASR | `{"text": content}` |
| `video` | 融合文本 + 代表帧 `{"image": media_url}` | `{"image": media_url}` |

官方 Rerank 请求的多模态文档项是文本或图片对象，当前不把一个文档拼成未被官方
文档声明的混合对象。因此图片/视频优先发送代表图像，语音内容已经保留在 Chunk
文本中并参与 Embedding/BM25；需要同时让 Rerank 看语音和画面时，应用层可将转写
内容拼入查询，或在后续升级时按 API 新能力扩展。

私有 `minio://` 路径必须由应用层回调转换成短时 presigned HTTPS URL，避免把内部
对象存储地址直接发给硅基流动。没有可访问的媒体 URL 时，代码会安全回退到文本
描述，而不是发送本地路径。

## 配置

```bash
SILICONFLOW_API_KEY=填入你的 Key
RAG_EMBEDDING_MODEL=Qwen/Qwen3-VL-Embedding-8B
RAG_RERANK_MODEL=Qwen/Qwen3-VL-Reranker-8B
```

Embedding 的 `RAG_EMBEDDING_DIMENSIONS` 可留空，使用 API 返回的原生维度；如果
服务端支持并且团队已经确定 Qdrant 集合维度，再显式填写。Embedding、Rerank 的
请求地址、超时和 provider-specific Key 都可以通过 [`.env.example`](../.env.example)
覆盖。

## 官方依据

- [SiliconFlow 创建嵌入请求](https://api-docs.siliconflow.cn/docs/api/embeddings-post)
- [SiliconFlow 创建重排序请求](https://api-docs.siliconflow.cn/docs/api/rerank-post)
- [SiliconFlow 获取用户模型列表](https://api-docs.siliconflow.cn/docs/api/models-get)
