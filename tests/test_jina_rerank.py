import unittest

from rag_engine.models import Chunk, RetrievalCandidate
from rag_engine.rerank import (
    JinaRerankConfig,
    JinaReranker,
    RerankAPIError,
)


class RecordingRerankTransport:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def post_json(self, url, *, headers, payload, timeout):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout": timeout,
            }
        )
        return self.response


def candidate(chunk_id: str, source_type: str, content: str, media_path: str | None = None):
    return RetrievalCandidate(
        chunk=Chunk(
            chunk_id,
            "file-1",
            source_type,
            content,
            media_path=media_path,
        ),
        score=0.1,
        source="dense",
    )


class JinaRerankerTests(unittest.TestCase):
    def test_from_env_uses_common_jina_key(self) -> None:
        config = JinaRerankConfig.from_env(
            {"RAG_RERANK_API_KEY": "", "JINA_API_KEY": "secret"}
        )

        self.assertEqual(config.api_key, "secret")
        self.assertEqual(config.model, "jina-reranker-v3")
        self.assertEqual(config.url, "https://api.jina.ai/v1/rerank")

    def test_sends_text_documents_to_jina_reranker(self) -> None:
        transport = RecordingRerankTransport(
            {
                "results": [
                    {"index": 2, "relevance_score": 0.95},
                    {"index": 0, "relevance_score": 0.70},
                ]
            }
        )
        reranker = JinaReranker(
            JinaRerankConfig(api_key="test-token"),
            transport=transport,
        )
        candidates = [
            candidate("doc", "document", "任务状态机"),
            candidate(
                "image",
                "image",
                "系统架构图",
                "https://cdn.example/architecture.png",
            ),
            candidate(
                "video",
                "video",
                "终端配置环境变量",
                "https://cdn.example/frame-10.jpg",
            ),
        ]

        ranked = reranker.rerank("视频里如何配置环境变量？", candidates, top_k=2)

        self.assertEqual([item.chunk_id for item in ranked], ["video", "doc"])
        self.assertEqual(ranked[0].rerank_score, 0.95)
        payload = transport.calls[0]["payload"]
        self.assertEqual(payload["model"], "jina-reranker-v3")
        self.assertEqual(payload["query"], "视频里如何配置环境变量？")
        self.assertEqual(payload["top_n"], 2)
        self.assertEqual(
            payload["documents"],
            [
                "任务状态机",
                "系统架构图",
                "终端配置环境变量",
            ],
        )
        self.assertEqual(
            transport.calls[0]["headers"]["Authorization"],
            "Bearer test-token",
        )

    def test_private_media_can_be_resolved_before_rerank(self) -> None:
        transport = RecordingRerankTransport(
            {"results": [{"index": 0, "relevance_score": 0.8}]}
        )
        reranker = JinaReranker(
            JinaRerankConfig(api_key="test-token"),
            transport=transport,
        )

        reranker.rerank(
            "查询",
            [candidate("image", "image", "图像", "minio://frames/1.jpg")],
        )

        self.assertEqual(
            transport.calls[0]["payload"]["documents"],
            ["图像"],
        )

    def test_invalid_response_is_rejected(self) -> None:
        reranker = JinaReranker(
            JinaRerankConfig(api_key="test-token"),
            transport=RecordingRerankTransport({"results": [{"index": 8}]}),
        )

        with self.assertRaises(RerankAPIError):
            reranker.rerank("查询", [candidate("doc", "document", "内容")])


if __name__ == "__main__":
    unittest.main()
