import tempfile
import unittest
from pathlib import Path

from ingestion.media import (
    ApiImageCaptioner,
    ApiTranscriber,
    FrameSample,
    MediaAPIConfig,
    VideoIngestionPipeline,
    ingest_audio,
)
from ingestion.types import TranscriptSegment


class FakeExtractor:
    def extract_audio(self, video_path: Path, output_dir: Path) -> Path:
        self.audio_request = (video_path, output_dir)
        return output_dir / "audio.wav"

    def extract_frames(
        self,
        video_path: Path,
        output_dir: Path,
        *,
        interval_seconds: float,
    ) -> list[FrameSample]:
        self.frame_request = (video_path, output_dir, interval_seconds)
        return [
            FrameSample(5, output_dir / "frame_000001.jpg"),
            FrameSample(35, output_dir / "frame_000002.jpg"),
        ]


class FakeTranscriber:
    def transcribe(self, audio_path: Path) -> list[TranscriptSegment]:
        self.audio_path = audio_path
        return [
            TranscriptSegment(2, 9, "打开配置文件"),
            TranscriptSegment(31, 38, "重启服务"),
        ]


class FakeCaptioner:
    def caption(self, image: str | Path) -> str:
        return f"画面 {Path(image).stem}"


class RecordingJsonTransport:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def post_json(self, url, *, headers, payload, timeout):
        self.calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout})
        return self.response


class RecordingMultipartTransport:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def post_file(self, url, *, headers, data, file_path, timeout):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "data": data,
                "file_path": file_path,
                "timeout": timeout,
            }
        )
        return self.response


class MediaPipelineTests(unittest.TestCase):
    def test_video_pipeline_extracts_transcribes_captions_and_aligns(self) -> None:
        extractor = FakeExtractor()
        transcriber = FakeTranscriber()
        pipeline = VideoIngestionPipeline(extractor, transcriber, FakeCaptioner())

        with tempfile.TemporaryDirectory() as directory:
            chunks = pipeline.ingest(
                Path("demo.mp4"),
                file_id="video-1",
                work_dir=Path(directory),
                frame_interval_seconds=5,
                window_seconds=30,
            )

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].source_type, "video")
        self.assertIn("打开配置文件", chunks[0].content)
        self.assertIn("frame_000001", chunks[0].content)
        self.assertEqual(chunks[1].time_start, 31)
        self.assertEqual(chunks[0].extra["source_media_path"], "demo.mp4")

    def test_audio_pipeline_preserves_transcript_timestamps(self) -> None:
        chunks = ingest_audio(
            Path("lesson.mp3"),
            file_id="audio-1",
            transcriber=FakeTranscriber(),
            window_seconds=30,
        )

        self.assertEqual([chunk.source_type for chunk in chunks], ["audio", "audio"])
        self.assertEqual(chunks[0].time_start, 2)
        self.assertEqual(chunks[0].time_end, 9)
        self.assertIn("打开配置文件", chunks[0].content)
        self.assertEqual(chunks[0].extra["source_media_path"], "lesson.mp3")

    def test_transcription_and_caption_clients_use_configured_apis(self) -> None:
        config = MediaAPIConfig(
            transcription_url="https://api.example/transcriptions",
            transcription_api_key="transcription-token",
            transcription_model="whisper-model",
            vision_url="https://api.example/chat/completions",
            vision_api_key="vision-token",
            vision_model="vision-model",
        )
        multipart = RecordingMultipartTransport(
            {
                "segments": [
                    {"start": 1.5, "end": 3.0, "text": "测试转写"},
                ]
            }
        )
        transcriber = ApiTranscriber(config, transport=multipart)
        json_transport = RecordingJsonTransport(
            {"choices": [{"message": {"content": "一张系统架构图"}}]}
        )
        captioner = ApiImageCaptioner(config, transport=json_transport)

        segments = transcriber.transcribe(Path("audio.wav"))
        caption = captioner.caption("https://cdn.example/frame.jpg")

        self.assertEqual(segments[0], TranscriptSegment(1.5, 3.0, "测试转写"))
        self.assertEqual(multipart.calls[0]["data"]["model"], "whisper-model")
        self.assertEqual(caption, "一张系统架构图")
        content = json_transport.calls[0]["payload"]["messages"][0]["content"]
        self.assertEqual(content[1]["image_url"]["url"], "https://cdn.example/frame.jpg")


if __name__ == "__main__":
    unittest.main()
