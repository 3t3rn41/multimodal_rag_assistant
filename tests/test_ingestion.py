import unittest

from ingestion import (
    DocumentBlock,
    FrameDescription,
    TranscriptSegment,
    chunk_document,
    chunk_media,
    image_chunk,
)
from rag_engine.retrieval import BM25Retriever


class DocumentChunkingTests(unittest.TestCase):
    def test_document_chunks_keep_contract_metadata_and_overlap(self) -> None:
        blocks = [
            DocumentBlock(
                text="这是一个很长的段落，用来验证切片之间会保留重叠上下文。",
                page=3,
                heading="配置说明",
            )
        ]

        chunks = chunk_document(
            "manual.pdf",
            blocks,
            max_chars=14,
            overlap_chars=4,
        )

        self.assertGreater(len(chunks), 1)
        self.assertEqual([chunk.page for chunk in chunks], [3] * len(chunks))
        self.assertEqual(chunks[0].source_type, "document")
        self.assertIn("配置说明", chunks[0].content)
        self.assertTrue(set(chunks[0].content[-4:]) & set(chunks[1].content[:4]))

    def test_image_is_one_chunk_with_media_path(self) -> None:
        chunk = image_chunk(
            "diagram.png",
            description="系统架构图，展示检索和生成链路。",
            media_path="minio://raw-files/diagram.png",
        )

        self.assertEqual(chunk.source_type, "image")
        self.assertEqual(chunk.media_path, "minio://raw-files/diagram.png")
        self.assertEqual(chunk.extra["modality"], "image")

    def test_document_chunks_are_ready_for_c_retrieval(self) -> None:
        chunks = chunk_document(
            "manual.pdf",
            [DocumentBlock("Redis 任务队列配置", page=3)],
        )

        results = BM25Retriever(chunks).search("Redis 队列", top_k=1)

        self.assertEqual(results[0].chunk_id, chunks[0].chunk_id)

    def test_media_chunks_fuse_transcript_and_frames_by_time_window(self) -> None:
        transcripts = [
            TranscriptSegment(2, 9, "先打开配置文件"),
            TranscriptSegment(31, 37, "然后重启服务"),
        ]
        frames = [
            FrameDescription(5, "终端显示配置文件", "frames/5.jpg"),
            FrameDescription(34, "终端显示重启命令", "frames/34.jpg"),
        ]

        chunks = chunk_media(
            "demo.mp4",
            transcripts,
            frames,
            window_seconds=30,
        )

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].time_start, 0)
        self.assertEqual(chunks[0].time_end, 30)
        self.assertIn("先打开配置文件", chunks[0].content)
        self.assertIn("终端显示配置文件", chunks[0].content)
        self.assertEqual(chunks[0].extra["frame_paths"], ["frames/5.jpg"])
        self.assertEqual(chunks[1].time_start, 30)
        self.assertEqual(chunks[1].media_path, "frames/34.jpg")

    def test_invalid_media_intervals_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            TranscriptSegment(10, 10, "没有有效时长")

        with self.assertRaises(ValueError):
            chunk_media("demo.mp4", [], [], window_seconds=0)


if __name__ == "__main__":
    unittest.main()
