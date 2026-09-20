import json
import unittest
from pathlib import Path

from ingestion import (
    DocumentBlock,
    FrameDescription,
    TranscriptSegment,
    chunk_document,
    chunk_media,
    image_chunk,
)


class IngestionQualitySampleTests(unittest.TestCase):
    def test_all_quality_samples_produce_contract_complete_chunks(self) -> None:
        sample_path = Path(__file__).parents[1] / "evaluation" / "ingestion_samples.jsonl"
        rows = [json.loads(line) for line in sample_path.read_text().splitlines()]

        self.assertEqual({row["source_type"] for row in rows}, {"document", "image", "audio", "video"})
        for row in rows:
            chunks = self._build_chunks(row)
            self.assertTrue(chunks, row["sample_id"])
            expected = row["expected"]
            for chunk in chunks:
                for field in expected["required_fields"]:
                    self.assertIsNotNone(getattr(chunk, field), f"{row['sample_id']}:{field}")
            content = "\n".join(chunk.content for chunk in chunks)
            for fragment in expected["content_contains"]:
                self.assertIn(fragment, content, row["sample_id"])

    @staticmethod
    def _build_chunks(row: dict[str, object]):
        source_type = row["source_type"]
        data = row["input"]
        if source_type == "document":
            return chunk_document(
                data["file_id"],
                [DocumentBlock(**block) for block in data["blocks"]],
            )
        if source_type == "image":
            return [image_chunk(data["file_id"], **{
                "description": data["description"],
                "media_path": data["media_path"],
            })]
        transcripts = [
            TranscriptSegment(**segment)
            for segment in data.get("transcripts", [])
        ]
        frames = [
            FrameDescription(**frame)
            for frame in data.get("frames", [])
        ]
        return chunk_media(data["file_id"], transcripts, frames, source_type=source_type)


if __name__ == "__main__":
    unittest.main()
