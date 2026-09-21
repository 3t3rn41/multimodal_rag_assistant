"""Export ingestion records as UTF-8 ``Chunk`` JSONL for vector indexing."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from ingestion import DocumentBlock, FrameDescription, TranscriptSegment
from ingestion import chunk_document, chunk_media, image_chunk
from ingestion.media import FFmpegMediaExtractor, clip_chunk_media, is_media_reference


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="UTF-8 JSONL containing document/image/audio/video ingestion records",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--text-only",
        action="store_true",
        help="drop media references; useful only for placeholder evaluation URLs",
    )
    parser.add_argument(
        "--clip-media",
        action="store_true",
        help="crop local audio/video sources to each chunk's evidence interval",
    )
    parser.add_argument(
        "--media-work-dir",
        type=Path,
        help="directory for local media clips; defaults to <output>/media_clips",
    )
    parser.add_argument(
        "--media-url-base",
        help="HTTP(S) base URL for uploaded clips, e.g. https://cdn.example/chunks",
    )
    parser.add_argument(
        "--media-minio-prefix",
        help="MinIO object prefix for uploaded clips, e.g. extracted-chunks",
    )
    return parser


def read_records(path: Path) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from exc
            if not isinstance(row, Mapping):
                raise ValueError(f"record at {path}:{line_number} must be an object")
            records.append(row)
    return records


def build_chunks(
    records: Iterable[Mapping[str, Any]],
    *,
    clip_media: bool = False,
    media_work_dir: Path | None = None,
    media_clipper: Any | None = None,
    media_ref_resolver: Any | None = None,
) -> list[Any]:
    chunks: list[Any] = []
    for row in records:
        source_type = str(row.get("source_type", ""))
        data = row.get("input")
        if not isinstance(data, Mapping):
            raise ValueError("each record must contain an object under 'input'")
        file_id = str(data.get("file_id", ""))
        if source_type == "document":
            chunks.extend(
                chunk_document(
                    file_id,
                    [DocumentBlock(**block) for block in data.get("blocks", [])],
                )
            )
        elif source_type == "image":
            chunks.append(
                image_chunk(
                    file_id,
                    description=str(data["description"]),
                    media_path=str(data["media_path"]),
                )
            )
        elif source_type in {"audio", "video"}:
            transcripts = [
                TranscriptSegment(**segment)
                for segment in data.get("transcripts", [])
            ]
            frames = [
                FrameDescription(**frame)
                for frame in data.get("frames", [])
            ]
            source_media_path = data.get("source_media_path")
            source_media_path = (
                str(source_media_path) if source_media_path is not None else None
            )
            if clip_media:
                if not source_media_path or is_media_reference(source_media_path):
                    raise ValueError(
                        "--clip-media requires a local source_media_path; "
                        "remote media must be cropped upstream"
                    )
                if media_work_dir is None or media_ref_resolver is None:
                    raise ValueError(
                        "--clip-media requires --media-work-dir and a remote "
                        "reference option"
                    )
            elif source_media_path and not is_media_reference(source_media_path):
                raise ValueError(
                    "local media path cannot enter the Chunk JSONL; provide a "
                    "remote media reference or use --clip-media"
                )

            media_chunks = chunk_media(
                file_id,
                transcripts,
                frames,
                source_type=source_type,
                source_media_path=source_media_path,
            )
            if clip_media:
                media_chunks = clip_chunk_media(
                    media_chunks,
                    Path(source_media_path),
                    media_work_dir,
                    media_clipper or FFmpegMediaExtractor(),
                    media_ref_resolver=media_ref_resolver,
                )
            chunks.extend(media_chunks)
        else:
            raise ValueError(f"unsupported source_type: {source_type!r}")
    _validate_media_references(chunks)
    return chunks


def _without_media(chunks: Iterable[Any]) -> list[Any]:
    text_chunks: list[Any] = []
    for chunk in chunks:
        extra = dict(chunk.extra)
        extra.pop("source_media_path", None)
        text_chunks.append(replace(chunk, media_path=None, extra=extra))
    return text_chunks


def write_chunks(path: Path, chunks: Iterable[Any]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as target:
        for chunk in chunks:
            target.write(
                json.dumps(
                    chunk.to_payload(),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
            count += 1
    return count


def _validate_media_references(chunks: Iterable[Any]) -> None:
    for chunk in chunks:
        values: list[str | None] = []
        if chunk.source_type == "image":
            values.append(chunk.media_path)
        elif chunk.source_type in {"audio", "video"}:
            values.append(chunk.extra.get("source_media_path"))
            if chunk.source_type == "video":
                values.append(chunk.media_path)
        for value in values:
            if value and not is_media_reference(str(value)):
                raise ValueError(
                    "Chunk JSONL contains a local media path; use minio://, "
                    "HTTP(S), or data references before indexing"
                )


def _media_ref_resolver(
    *,
    media_url_base: str | None,
    media_minio_prefix: str | None,
) -> Any | None:
    if media_url_base and media_minio_prefix:
        raise ValueError("choose only one of --media-url-base and --media-minio-prefix")
    if media_url_base:
        base = media_url_base.rstrip("/")
        return lambda path: f"{base}/{path.name}"
    if media_minio_prefix:
        prefix = media_minio_prefix.removeprefix("minio://").strip("/")
        if not prefix:
            raise ValueError("--media-minio-prefix must not be empty")
        return lambda path: f"minio://{prefix}/{path.name}"
    return None


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    resolver = _media_ref_resolver(
        media_url_base=args.media_url_base,
        media_minio_prefix=args.media_minio_prefix,
    )
    work_dir = args.media_work_dir
    if args.clip_media and work_dir is None:
        work_dir = args.output.parent / "media_clips"
    chunks = build_chunks(
        read_records(args.input),
        clip_media=args.clip_media,
        media_work_dir=work_dir,
        media_ref_resolver=resolver,
    )
    if args.text_only:
        chunks = _without_media(chunks)
    count = write_chunks(args.output, chunks)
    print(json.dumps({"chunks": count, "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
