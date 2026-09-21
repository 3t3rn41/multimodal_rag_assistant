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


def build_chunks(records: Iterable[Mapping[str, Any]]) -> list[Any]:
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
            chunks.extend(
                chunk_media(
                    file_id,
                    transcripts,
                    frames,
                    source_type=source_type,
                    source_media_path=(
                        str(source_media_path)
                        if source_media_path is not None
                        else None
                    ),
                )
            )
        else:
            raise ValueError(f"unsupported source_type: {source_type!r}")
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


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    chunks = build_chunks(read_records(args.input))
    if args.text_only:
        chunks = _without_media(chunks)
    count = write_chunks(args.output, chunks)
    print(json.dumps({"chunks": count, "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
