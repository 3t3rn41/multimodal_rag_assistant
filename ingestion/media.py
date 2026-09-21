"""Audio/video extraction, API transcription, captioning, and alignment."""

from __future__ import annotations

import base64
import mimetypes
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from rag_engine.models import Chunk

from .api_embeddings import HttpxJsonTransport, JsonTransport
from .chunking import chunk_media
from .types import FrameDescription, TranscriptSegment


@dataclass(frozen=True, slots=True)
class FrameSample:
    timestamp: float
    path: Path


class MediaExtractor(Protocol):
    def extract_audio(self, video_path: Path, output_dir: Path) -> Path: ...

    def extract_frames(
        self,
        video_path: Path,
        output_dir: Path,
        *,
        interval_seconds: float,
    ) -> list[FrameSample]: ...

    def clip_media(
        self,
        media_path: Path,
        output_dir: Path,
        *,
        start_seconds: float,
        end_seconds: float,
    ) -> Path: ...


class MediaClipper(Protocol):
    def clip_media(
        self,
        media_path: Path,
        output_dir: Path,
        *,
        start_seconds: float,
        end_seconds: float,
    ) -> Path: ...


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> list[TranscriptSegment]: ...


class ImageCaptioner(Protocol):
    def caption(self, image: str | Path) -> str: ...


class FFmpegMediaExtractor:
    """Use the system FFmpeg binary without shell interpolation."""

    def __init__(
        self,
        *,
        ffmpeg_binary: str = "ffmpeg",
        runner: Any = subprocess.run,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.runner = runner

    def extract_audio(self, video_path: Path, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"{video_path.stem}.wav"
        self._run(
            [
                self.ffmpeg_binary,
                "-y",
                "-i",
                str(video_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                str(output),
            ]
        )
        return output

    def extract_frames(
        self,
        video_path: Path,
        output_dir: Path,
        *,
        interval_seconds: float,
    ) -> list[FrameSample]:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        output_dir.mkdir(parents=True, exist_ok=True)
        pattern = output_dir / "frame_%06d.jpg"
        self._run(
            [
                self.ffmpeg_binary,
                "-y",
                "-i",
                str(video_path),
                "-vf",
                f"fps=1/{interval_seconds:g}",
                "-q:v",
                "2",
                str(pattern),
            ]
        )
        paths = sorted(output_dir.glob("frame_*.jpg"))
        return [
            FrameSample(index * interval_seconds, path)
            for index, path in enumerate(paths)
        ]

    def clip_media(
        self,
        media_path: Path,
        output_dir: Path,
        *,
        start_seconds: float,
        end_seconds: float,
    ) -> Path:
        if start_seconds < 0 or end_seconds <= start_seconds:
            raise ValueError("media clip must have a positive time range")
        output_dir.mkdir(parents=True, exist_ok=True)
        duration = end_seconds - start_seconds
        output = output_dir / (
            f"{media_path.stem}_{start_seconds:g}-{end_seconds:g}"
            f"{media_path.suffix or '.mp4'}"
        )
        self._run(
            [
                self.ffmpeg_binary,
                "-y",
                "-ss",
                f"{start_seconds:.3f}",
                "-i",
                str(media_path),
                "-t",
                f"{duration:.3f}",
                "-c",
                "copy",
                "-avoid_negative_ts",
                "make_zero",
                str(output),
            ]
        )
        return output

    def _run(self, command: list[str]) -> None:
        try:
            self.runner(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise RuntimeError(
                "FFmpeg is required for audio extraction and frame sampling"
            ) from exc


@dataclass(frozen=True, slots=True)
class MediaAPIConfig:
    transcription_url: str
    transcription_api_key: str
    transcription_model: str
    vision_url: str
    vision_api_key: str
    vision_model: str
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "MediaAPIConfig":
        values = os.environ if env is None else env
        required = {
            "RAG_TRANSCRIPTION_API_KEY": values.get("RAG_TRANSCRIPTION_API_KEY", ""),
            "RAG_VISION_API_KEY": values.get("RAG_VISION_API_KEY", ""),
        }
        missing = [key for key, value in required.items() if not value.strip()]
        if missing:
            raise ValueError("missing media API keys: " + ", ".join(missing))
        return cls(
            transcription_url=values.get(
                "RAG_TRANSCRIPTION_API_URL",
                "https://api.openai.com/v1/audio/transcriptions",
            ),
            transcription_api_key=required["RAG_TRANSCRIPTION_API_KEY"],
            transcription_model=values.get("RAG_TRANSCRIPTION_MODEL", "whisper-1"),
            vision_url=values.get(
                "RAG_VISION_API_URL",
                "https://api.openai.com/v1/chat/completions",
            ),
            vision_api_key=required["RAG_VISION_API_KEY"],
            vision_model=values.get("RAG_VISION_MODEL", "gpt-4o-mini"),
            timeout_seconds=float(values.get("RAG_MEDIA_API_TIMEOUT_SECONDS", "60")),
        )


class MultipartTransport(Protocol):
    def post_file(
        self,
        url: str,
        *,
        headers: dict[str, str],
        data: dict[str, str],
        file_path: Path,
        timeout: float,
    ) -> Mapping[str, Any]: ...


class HttpxMultipartTransport:
    def post_file(
        self,
        url: str,
        *,
        headers: dict[str, str],
        data: dict[str, str],
        file_path: Path,
        timeout: float,
    ) -> Mapping[str, Any]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("media API clients require the 'api' extra") from exc
        mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        try:
            with file_path.open("rb") as file_handle:
                response = httpx.post(
                    url,
                    headers=headers,
                    data=data,
                    files={"file": (file_path.name, file_handle, mime)},
                    timeout=timeout,
                )
            response.raise_for_status()
            response_data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"transcription API request failed: {exc}") from exc
        if not isinstance(response_data, Mapping):
            raise RuntimeError("transcription API response must be an object")
        return response_data


class ApiTranscriber:
    def __init__(
        self,
        config: MediaAPIConfig,
        *,
        transport: MultipartTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or HttpxMultipartTransport()

    def transcribe(self, audio_path: Path) -> list[TranscriptSegment]:
        response = self.transport.post_file(
            self.config.transcription_url,
            headers={"Authorization": f"Bearer {self.config.transcription_api_key}"},
            data={
                "model": self.config.transcription_model,
                "response_format": "verbose_json",
                "timestamp_granularities[]": "segment",
            },
            file_path=audio_path,
            timeout=self.config.timeout_seconds,
        )
        segments = response.get("segments")
        if not isinstance(segments, list):
            raise RuntimeError("transcription API must return timestamped segments")
        return [
            TranscriptSegment(
                float(segment["start"]),
                float(segment["end"]),
                str(segment["text"]),
            )
            for segment in segments
        ]


class ApiImageCaptioner:
    def __init__(
        self,
        config: MediaAPIConfig,
        *,
        transport: JsonTransport | None = None,
        prompt: str = "Describe the image for multimodal retrieval, including visible text and chart values.",
    ) -> None:
        self.config = config
        self.transport = transport or HttpxJsonTransport()
        self.prompt = prompt

    def caption(self, image: str | Path) -> str:
        image_url = _image_reference(image)
        response = self.transport.post_json(
            self.config.vision_url,
            headers={
                "Authorization": f"Bearer {self.config.vision_api_key}",
                "Content-Type": "application/json",
            },
            payload={
                "model": self.config.vision_model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self.prompt},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    }
                ],
            },
            timeout=self.config.timeout_seconds,
        )
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("vision API response has no message content") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("vision API returned an empty caption")
        return content.strip()


class VideoIngestionPipeline:
    def __init__(
        self,
        extractor: MediaExtractor,
        transcriber: Transcriber,
        captioner: ImageCaptioner,
    ) -> None:
        self.extractor = extractor
        self.transcriber = transcriber
        self.captioner = captioner

    def ingest(
        self,
        video_path: Path,
        *,
        file_id: str,
        work_dir: Path,
        frame_interval_seconds: float = 5.0,
        window_seconds: float = 30.0,
    ):
        audio_path = self.extractor.extract_audio(video_path, work_dir)
        frames = self.extractor.extract_frames(
            video_path,
            work_dir,
            interval_seconds=frame_interval_seconds,
        )
        transcripts = self.transcriber.transcribe(audio_path)
        descriptions = [
            FrameDescription(
                timestamp=frame.timestamp,
                description=self.captioner.caption(frame.path),
                media_path=str(frame.path),
            )
            for frame in frames
        ]
        chunks = chunk_media(
            file_id,
            transcripts,
            descriptions,
            source_type="video",
            window_seconds=window_seconds,
        )
        return _clip_chunks(chunks, video_path, work_dir, self.extractor)


def ingest_audio(
    audio_path: Path,
    *,
    file_id: str,
    transcriber: Transcriber,
    window_seconds: float = 30.0,
    media_clipper: MediaClipper | None = None,
    work_dir: Path | None = None,
):
    """Transcribe audio and reuse the same timestamped media fusion contract."""

    chunks = chunk_media(
        file_id,
        transcriber.transcribe(audio_path),
        [],
        source_type="audio",
        window_seconds=window_seconds,
    )
    clipper = media_clipper or FFmpegMediaExtractor()
    return _clip_chunks(
        chunks,
        audio_path,
        work_dir or audio_path.parent,
        clipper,
    )


def _clip_chunks(
    chunks: list[Chunk],
    source_path: Path,
    output_dir: Path,
    clipper: MediaClipper,
) -> list[Chunk]:
    clipped: list[Chunk] = []
    for chunk in chunks:
        start_seconds, end_seconds = _clip_bounds(chunk)
        clip_path = clipper.clip_media(
            source_path,
            output_dir,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        )
        extra = dict(chunk.extra)
        extra["source_media_path"] = str(clip_path)
        extra["original_media_path"] = str(source_path)
        media_path = str(clip_path) if chunk.source_type == "audio" else chunk.media_path
        clipped.append(replace(chunk, media_path=media_path, extra=extra))
    return clipped


def _clip_bounds(chunk: Chunk) -> tuple[float, float]:
    start = chunk.time_start
    end = chunk.time_end
    if start is not None and end is not None and end > start:
        return float(start), float(end)
    window_start = chunk.extra.get("window_start")
    window_end = chunk.extra.get("window_end")
    if isinstance(window_start, (int, float)) and isinstance(window_end, (int, float)):
        if window_end > window_start:
            return float(window_start), float(window_end)
    raise ValueError(f"chunk {chunk.chunk_id!r} has no positive media time range")


def _image_reference(image: str | Path) -> str:
    if isinstance(image, str) and image.startswith(("https://", "http://", "data:")):
        return image
    path = Path(image)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"
