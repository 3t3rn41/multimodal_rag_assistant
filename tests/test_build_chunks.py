import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_ingestion_chunks import main


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


if __name__ == "__main__":
    unittest.main()
