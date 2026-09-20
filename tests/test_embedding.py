import unittest

from ingestion import embed_and_upsert, embed_chunks
from rag_engine.models import Chunk


class FakeEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0] for text in texts]


class RecordingWriter:
    def __init__(self) -> None:
        self.batches: list[tuple[Chunk, ...]] = []

    def upsert(self, chunks: tuple[Chunk, ...]) -> int:
        self.batches.append(chunks)
        return len(chunks)


class EmbeddingTests(unittest.TestCase):
    def test_embed_chunks_returns_c_compatible_chunks(self) -> None:
        chunks = [
            Chunk("c1", "doc.pdf", "document", "第一段"),
            Chunk("c2", "doc.pdf", "document", "第二段"),
        ]

        embedded = embed_chunks(chunks, FakeEmbedder(), batch_size=1)

        self.assertEqual([chunk.embedding for chunk in embedded], [(3.0, 1.0), (3.0, 1.0)])
        self.assertEqual([chunk.chunk_id for chunk in embedded], ["c1", "c2"])
        self.assertIsNone(chunks[0].embedding)

    def test_embed_and_upsert_batches_payload_ready_chunks(self) -> None:
        chunks = [
            Chunk("c1", "doc.pdf", "document", "第一段"),
            Chunk("c2", "doc.pdf", "document", "第二段"),
            Chunk("c3", "doc.pdf", "document", "第三段"),
        ]
        writer = RecordingWriter()

        count = embed_and_upsert(
            chunks,
            FakeEmbedder(),
            writer,
            batch_size=2,
        )

        self.assertEqual(count, 3)
        self.assertEqual([len(batch) for batch in writer.batches], [2, 1])
        self.assertEqual(writer.batches[0][0].to_payload()["content"], "第一段")
        self.assertEqual(writer.batches[0][0].embedding, (3.0, 1.0))

    def test_embedding_provider_result_length_must_match_batch(self) -> None:
        class ShortEmbedder:
            def embed(self, texts: list[str]) -> list[list[float]]:
                return []

        with self.assertRaises(ValueError):
            embed_chunks([Chunk("c1", "doc.pdf", "document", "文本")], ShortEmbedder())


if __name__ == "__main__":
    unittest.main()
