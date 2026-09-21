import unittest
from pathlib import Path

from rag_engine.models import Chunk
from scripts.index_chunks import build_parser, validate_media_references


class IndexCommandTests(unittest.TestCase):
    def test_defaults_to_a_jina_specific_collection_and_supports_rebuild(self) -> None:
        args = build_parser().parse_args(["--chunks", str(Path("chunks.jsonl")), "--rebuild"])

        self.assertTrue(args.rebuild)
        self.assertEqual(args.collection, "jina_v5_omni_small_1024")
        self.assertEqual(args.embedding_dimensions, 1024)
        self.assertIsNone(args.qdrant_path)

    def test_local_media_reference_is_rejected_before_embedding(self) -> None:
        chunk = Chunk(
            "audio-1",
            "lesson.mp3",
            "audio",
            "转写",
            extra={"source_media_path": r"C:\clips\lesson-2-9.mp3"},
        )

        with self.assertRaisesRegex(ValueError, "remote media reference"):
            validate_media_references([chunk], lambda value: None)

    def test_minio_media_reference_must_resolve_to_http_url(self) -> None:
        chunk = Chunk(
            "image-1",
            "diagram.png",
            "image",
            "架构图",
            media_path="minio://raw-files/diagram.png",
        )

        with self.assertRaisesRegex(ValueError, "does not resolve"):
            validate_media_references([chunk], lambda value: None)


if __name__ == "__main__":
    unittest.main()
