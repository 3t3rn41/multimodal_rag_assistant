import math
import unittest

from ingestion.api_embeddings import (
    ApiMultimodalEmbedder,
    EmbeddingAPIError,
    MultimodalEmbeddingAPIConfig,
)
from rag_engine.models import Chunk


class RecordingTransport:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors
        self.calls: list[dict[str, object]] = []

    def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout: float,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout": timeout,
            }
        )
        return {
            "data": [
                {"index": index, "embedding": vector}
                for index, vector in enumerate(self.vectors)
            ]
        }


def config() -> MultimodalEmbeddingAPIConfig:
    return MultimodalEmbeddingAPIConfig(
        url="https://embedding.example/v1/embeddings",
        api_key="test-token",
        model="multimodal-model",
        dimensions=2,
        passage_task="retrieval.passage",
        query_task="retrieval.query",
        timeout_seconds=12,
    )


class ApiMultimodalEmbedderTests(unittest.TestCase):
    def test_from_env_uses_jina_key_and_tasks(self) -> None:
        with self.assertRaises(ValueError):
            MultimodalEmbeddingAPIConfig.from_env({})

        loaded = MultimodalEmbeddingAPIConfig.from_env(
            {
                "RAG_EMBEDDING_API_KEY": "",
                "JINA_API_KEY": "secret",
                "RAG_EMBEDDING_API_URL": "https://example.test/embed",
                "RAG_EMBEDDING_MODEL": "jina-embeddings-v5-omni-small",
                "RAG_EMBEDDING_PASSAGE_TASK": "retrieval.passage",
                "RAG_EMBEDDING_QUERY_TASK": "retrieval.query",
            }
        )
        self.assertEqual(loaded.api_key, "secret")
        self.assertEqual(loaded.model, "jina-embeddings-v5-omni-small")
        self.assertEqual(loaded.passage_task, "retrieval.passage")
        self.assertEqual(loaded.query_task, "retrieval.query")
        self.assertIsNone(loaded.dimensions)

    def test_chunks_use_text_and_media_in_one_embedding_space(self) -> None:
        # Inputs are: document text, image text/image, audio text/audio,
        # video text/raw video/representative frame.
        transport = RecordingTransport(
            [
                [1, 0],
                [1, 0],
                [0, 1],
                [2, 0],
                [0, 1],
                [1, 0],
                [0, 1],
                [0, 1],
            ]
        )
        provider = ApiMultimodalEmbedder(config(), transport=transport)
        chunks = [
            Chunk("doc", "manual.pdf", "document", "任务状态机"),
            Chunk(
                "image",
                "diagram.png",
                "image",
                "系统架构图",
                media_path="https://cdn.example/diagram.png",
            ),
            Chunk(
                "audio",
                "lesson.mp3",
                "audio",
                "音频转写内容",
                extra={"source_media_path": "https://cdn.example/lesson.mp3"},
            ),
            Chunk(
                "video",
                "demo.mp4",
                "video",
                "语音和画面融合内容",
                media_path="https://cdn.example/frame.jpg",
                extra={"source_media_path": "https://cdn.example/demo.mp4"},
            ),
        ]

        vectors = provider.embed_chunks(chunks)

        self.assertEqual(vectors[0], (1.0, 0.0))
        expected = math.sqrt(0.5)
        self.assertAlmostEqual(vectors[1][0], expected)
        self.assertAlmostEqual(vectors[1][1], expected)
        self.assertAlmostEqual(vectors[2][0], expected)
        self.assertAlmostEqual(vectors[2][1], expected)
        self.assertAlmostEqual(vectors[3][0], 1 / math.sqrt(5))
        self.assertAlmostEqual(vectors[3][1], 2 / math.sqrt(5))
        payload = transport.calls[0]["payload"]
        self.assertEqual(payload["model"], "multimodal-model")
        self.assertEqual(payload["dimensions"], 2)
        self.assertEqual(payload["encoding_format"], "float")
        self.assertEqual(payload["task"], "retrieval.passage")
        self.assertEqual(
            payload["input"],
            [
                {"text": "任务状态机"},
                {"text": "系统架构图"},
                {"image": "https://cdn.example/diagram.png"},
                {"text": "音频转写内容"},
                {"audio": "https://cdn.example/lesson.mp3"},
                {"text": "语音和画面融合内容"},
                {"video": "https://cdn.example/demo.mp4"},
                {"image": "https://cdn.example/frame.jpg"},
            ],
        )
        self.assertEqual(transport.calls[0]["headers"]["Authorization"], "Bearer test-token")

    def test_query_uses_same_multimodal_endpoint(self) -> None:
        transport = RecordingTransport([[0.25, 0.75]])
        provider = ApiMultimodalEmbedder(config(), transport=transport)

        vector = provider.embed_query("视频里讲了什么？")

        self.assertEqual(vector, [0.25, 0.75])
        self.assertEqual(
            transport.calls[0]["payload"]["input"],
            [{"text": "视频里讲了什么？"}],
        )
        self.assertEqual(
            transport.calls[0]["payload"]["task"],
            "retrieval.query",
        )

    def test_non_http_media_can_be_resolved_to_presigned_url(self) -> None:
        transport = RecordingTransport([[1, 0], [0, 1]])
        provider = ApiMultimodalEmbedder(
            config(),
            transport=transport,
            media_url_resolver=lambda value: value.replace(
                "minio://raw-files/", "https://storage.example/"
            ),
        )
        chunk = Chunk(
            "image",
            "diagram.png",
            "image",
            "架构图",
            media_path="minio://raw-files/diagram.png",
        )

        provider.embed_chunks([chunk])

        self.assertEqual(
            transport.calls[0]["payload"]["input"][1],
            {"image": "https://storage.example/diagram.png"},
        )

    def test_audio_and_video_paths_can_be_resolved_to_jina_inputs(self) -> None:
        transport = RecordingTransport(
            [[1, 0], [0, 1], [1, 0], [0, 1], [0, 1]]
        )
        provider = ApiMultimodalEmbedder(
            config(),
            transport=transport,
            media_url_resolver=lambda value: value.replace(
                "minio://raw-files/", "https://storage.example/"
            ),
        )
        chunks = [
            Chunk(
                "audio",
                "lesson.mp3",
                "audio",
                "音频",
                extra={"source_media_path": "minio://raw-files/lesson.mp3"},
            ),
            Chunk(
                "video",
                "demo.mp4",
                "video",
                "视频",
                media_path="minio://raw-files/frame.jpg",
                extra={"source_media_path": "minio://raw-files/demo.mp4"},
            ),
        ]

        provider.embed_chunks(chunks)

        self.assertEqual(
            transport.calls[0]["payload"]["input"],
            [
                {"text": "音频"},
                {"audio": "https://storage.example/lesson.mp3"},
                {"text": "视频"},
                {"video": "https://storage.example/demo.mp4"},
                {"image": "https://storage.example/frame.jpg"},
            ],
        )

    def test_invalid_api_response_is_rejected(self) -> None:
        transport = RecordingTransport([])
        provider = ApiMultimodalEmbedder(config(), transport=transport)

        with self.assertRaises(EmbeddingAPIError):
            provider.embed(["missing vector"])


if __name__ == "__main__":
    unittest.main()
