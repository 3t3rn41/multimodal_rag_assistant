# Jina 多模态 Embedding 与 Rerank

## 结论

项目运行时统一使用 Jina API，不下载或加载本地 Embedding/Rerank 模型：

- Embedding：`jina-embeddings-v5-omni-small`，请求
  `https://api.jina.ai/v1/embeddings`，默认 1024 维；
- Rerank：`jina-reranker-v3`，请求
  `https://api.jina.ai/v1/rerank`。

Jina `v5-omni` 将文本、图片、音频、视频和 PDF 放入共享向量空间。Chunk 的文本
描述仍然保留，音频和视频则在可访问 URL 存在时额外发送原始媒体；视频代表帧也可
作为补充视觉证据发送。

## 输入路由

| Chunk 类型 | Embedding API 输入 | Rerank API 文档输入 |
| --- | --- | --- |
| `document` | `{"text": content}` | `content` |
| `image` | 文本描述 + `{"image": media_url}`，向量归一化后取均值 | `content` |
| `audio` | `{"text": content}` + `{"audio": media_url}` | `content` |
| `video` | 融合文本 + `{"video": media_url}` + 可选 `{"image": frame_url}` | `content` |

Embedding 请求使用 `retrieval.passage`；查询向量使用 `retrieval.query`，并显式发送
`normalized: true` 与 `embedding_type: "float"`。Rerank
阶段使用 `content` 中已经对齐的转写和画面描述，避免把本地文件路径直接发给文本
重排模型。

私有 `minio://` 路径必须由应用层回调转换成短时 presigned HTTPS URL，避免把内部
对象存储地址直接发给 Jina。没有可访问的媒体 URL 时，代码会安全回退到文本
描述，而不是发送本地路径。

## 配置

```bash
JINA_API_KEY=填入你的 Key
RAG_EMBEDDING_MODEL=jina-embeddings-v5-omni-small
RAG_RERANK_MODEL=jina-reranker-v3
RAG_EMBEDDING_PASSAGE_TASK=retrieval.passage
RAG_EMBEDDING_QUERY_TASK=retrieval.query
```

Embedding 的 `RAG_EMBEDDING_DIMENSIONS` 默认填写 1024，以便和 Qdrant 集合维度
一致；Embedding、Rerank 的请求地址、超时和 provider-specific Key 都可以通过
[`.env.example`](../.env.example) 覆盖。

## 官方依据

- [Jina Embeddings API](https://jina.ai/en-US/embeddings/)
- [Jina v5-omni 发布说明](https://jina.ai/news/jina-embeddings-v5-omni-multimodal-embeddings-for-text-image-audio-and-video/)
- [Jina Rerank API](https://jina.ai/?model=jina-reranker-v3)
