import unittest

from rag_engine.models import Chunk, RetrievalCandidate
from rag_engine.rerank import (
    RerankAPIError,
    SiliconFlowRerankConfig,
    SiliconFlowReranker,
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


class SiliconFlowRerankerTests(unittest.TestCase):
    def test_from_env_uses_common_siliconflow_key(self) -> None:
        config = SiliconFlowRerankConfig.from_env(
            {"RAG_RERANK_API_KEY": "", "SILICONFLOW_API_KEY": "secret"}
        )

        self.assertEqual(config.api_key, "secret")
        self.assertEqual(config.model, "Qwen/Qwen3-VL-Reranker-8B")
        self.assertEqual(config.url, "https://api.siliconflow.cn/v1/rerank")

    def test_sends_text_and_image_documents_to_qwen_vl_reranker(self) -> None:
        transport = RecordingRerankTransport(
            {
                "results": [
                    {"index": 2, "relevance_score": 0.95},
                    {"index": 0, "relevance_score": 0.70},
                ]
            }
        )
        reranker = SiliconFlowReranker(
            SiliconFlowRerankConfig(api_key="test-token"),
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
        self.assertEqual(payload["model"], "Qwen/Qwen3-VL-Reranker-8B")
        self.assertEqual(payload["query"], "视频里如何配置环境变量？")
        self.assertEqual(payload["top_n"], 2)
        self.assertEqual(
            payload["documents"],
            [
                {"text": "任务状态机"},
                {"image": "https://cdn.example/architecture.png"},
                {"image": "https://cdn.example/frame-10.jpg"},
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
        reranker = SiliconFlowReranker(
            SiliconFlowRerankConfig(api_key="test-token"),
            transport=transport,
            media_url_resolver=lambda value: value.replace(
                "minio://frames/", "https://storage.example/"
            ),
        )

        reranker.rerank(
            "查询",
            [candidate("image", "image", "图像", "minio://frames/1.jpg")],
        )

        self.assertEqual(
            transport.calls[0]["payload"]["documents"],
            [{"image": "https://storage.example/1.jpg"}],
        )

    def test_invalid_response_is_rejected(self) -> None:
        reranker = SiliconFlowReranker(
            SiliconFlowRerankConfig(api_key="test-token"),
            transport=RecordingRerankTransport({"results": [{"index": 8}]}),
        )

        with self.assertRaises(RerankAPIError):
            reranker.rerank("查询", [candidate("doc", "document", "内容")])


if __name__ == "__main__":
    unittest.main()
