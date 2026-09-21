import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_ingestion_chunks import build_chunks, main


class BuildIngestionChunksTests(unittest.TestCase):
    def test_builds_utf8_chunk_jsonl_with_persisted_qdrant_ids(self) -> None:
        row = {
            "sample_id": "document",
            "source_type": "document",
            "input": {
                "file_id": "说明.pdf",
                "blocks": [{"text": "任务状态机", "page": 1}],
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.jsonl"
            output = Path(directory) / "chunks.jsonl"
            source.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

            self.assertEqual(main(["--input", str(source), "--output", str(output)]), 0)

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["content"], "任务状态机")
            self.assertTrue(payload["extra"]["qdrant_point_id"])

    def test_media_export_crops_chunks_and_persists_remote_references(self) -> None:
        class FakeClipper:
            def __init__(self) -> None:
                self.calls = []

            def clip_media(self, media_path, output_dir, *, start_seconds, end_seconds):
                self.calls.append((media_path, output_dir, start_seconds, end_seconds))
                return output_dir / f"clip-{start_seconds:g}-{end_seconds:g}.mp3"

        clipper = FakeClipper()
        row = {
            "source_type": "audio",
            "input": {
                "file_id": "lesson.mp3",
                "source_media_path": "lesson.mp3",
                "transcripts": [{"start": 2, "end": 9, "text": "配置服务"}],
            },
        }

        chunks = build_chunks(
            [row],
            clip_media=True,
            media_work_dir=Path("clips"),
            media_clipper=clipper,
            media_ref_resolver=lambda path: f"minio://chunks/{path.name}",
        )

        self.assertEqual(chunks[0].media_path, "minio://chunks/clip-2-9.mp3")
        self.assertEqual(
            chunks[0].extra["source_media_path"],
            "minio://chunks/clip-2-9.mp3",
        )
        self.assertEqual(clipper.calls[0][2:], (2.0, 9.0))

    def test_local_media_without_remote_reference_is_rejected(self) -> None:
        row = {
            "source_type": "audio",
            "input": {
                "file_id": "lesson.mp3",
                "source_media_path": "lesson.mp3",
                "transcripts": [{"start": 2, "end": 9, "text": "配置服务"}],
            },
        }

        with self.assertRaisesRegex(ValueError, "remote media reference"):
            build_chunks([row])


if __name__ == "__main__":
    unittest.main()
