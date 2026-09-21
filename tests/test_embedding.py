import unittest
from uuid import UUID, uuid4

from ingestion import (
    DocumentBlock,
    chunk_document,
    embed_and_upsert,
    embed_chunks,
    index_chunks,
)
from ingestion.embedding import _qdrant_point_id
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


class ResumableWriter(RecordingWriter):
    def __init__(self, existing: set[str]) -> None:
        super().__init__()
        self.existing = set(existing)

    def existing_chunk_ids(self, chunks: tuple[Chunk, ...] | list[Chunk]) -> set[str]:
        requested = {chunk.chunk_id for chunk in chunks}
        return requested & self.existing

    def upsert(self, chunks: tuple[Chunk, ...]) -> int:
        count = super().upsert(chunks)
        self.existing.update(chunk.chunk_id for chunk in chunks)
        return count


class EmbeddingTests(unittest.TestCase):
    def test_ingestion_persists_a_random_qdrant_uuid(self) -> None:
        chunk = chunk_document(
            "doc.pdf",
            [DocumentBlock("内容")],
        )[0]

        point_id = UUID(str(chunk.extra["qdrant_point_id"]))

        self.assertEqual(str(point_id), chunk.extra["qdrant_point_id"])

    def test_qdrant_point_id_requires_an_upstream_persisted_uuid(self) -> None:
        persisted = str(uuid4())
        chunk = Chunk(
            "not-a-uuid",
            "doc.pdf",
            "document",
            "内容",
            extra={"qdrant_point_id": persisted},
        )
        self.assertEqual(_qdrant_point_id(chunk), persisted)

        with self.assertRaisesRegex(ValueError, "persisted UUID"):
            _qdrant_point_id(Chunk("arbitrary-id", "doc.pdf", "document", "内容"))

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

    def test_payload_round_trip_is_compatible_with_c_model(self) -> None:
        chunk = embed_chunks(
            [Chunk("c1", "doc.pdf", "document", "第一段", page=3)],
            FakeEmbedder(),
        )[0]

        restored = Chunk.from_payload(chunk.to_payload(include_embedding=True))

        self.assertEqual(restored.chunk_id, "c1")
        self.assertEqual(restored.page, 3)
        self.assertEqual(restored.embedding, (3.0, 1.0))

    def test_embedding_provider_result_length_must_match_batch(self) -> None:
        class ShortEmbedder:
            def embed(self, texts: list[str]) -> list[list[float]]:
                return []

        with self.assertRaises(ValueError):
            embed_chunks([Chunk("c1", "doc.pdf", "document", "文本")], ShortEmbedder())

    def test_index_chunks_skips_existing_and_verifies_consistency(self) -> None:
        chunks = [
            Chunk("c1", "doc.pdf", "document", "第一段"),
            Chunk("c2", "doc.pdf", "document", "第二段"),
            Chunk("c3", "doc.pdf", "document", "第三段"),
        ]
        writer = ResumableWriter({"c1"})

        report = index_chunks(chunks, FakeEmbedder(), writer, batch_size=1)

        self.assertEqual(report.total, 3)
        self.assertEqual(report.skipped, 1)
        self.assertEqual(report.embedded, 2)
        self.assertEqual(report.upserted, 2)
        self.assertEqual([batch[0].chunk_id for batch in writer.batches], ["c2", "c3"])

    def test_index_chunks_fails_when_writer_cannot_confirm_all_chunks(self) -> None:
        class BrokenWriter(ResumableWriter):
            def upsert(self, chunks: tuple[Chunk, ...]) -> int:
                self.batches.append(chunks)
                return len(chunks)

        with self.assertRaisesRegex(RuntimeError, "consistency check failed"):
            index_chunks(
                [Chunk("c1", "doc.pdf", "document", "第一段")],
                FakeEmbedder(),
                BrokenWriter(set()),
            )


if __name__ == "__main__":
    unittest.main()
