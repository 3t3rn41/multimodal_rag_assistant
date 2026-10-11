"""Shared document parsing and verified, read-only citation locations.

Member B still produces the canonical chunks. These windows describe their
locations in the reader; they never create business IDs, vectors or point UUIDs.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from backend.task.errors import InvalidTextEncodingError
from ingestion import ParsedDocument, parse_document
from ingestion.types import DocumentBlock
from rag_engine.models import Chunk

DOCUMENT_MAX_CHARS = 1_200
DOCUMENT_OVERLAP_CHARS = 160
_DOCUMENT_SEQUENCE = re.compile(r":document:(\d+)$")


def decode_document_text(data: bytes) -> str:
    encodings = ("utf-16",) if data.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-8-sig", "gb18030")
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise InvalidTextEncodingError("文本编码无法识别，请将文件保存为 UTF-8、带 BOM 的 UTF-16 或 GB18030 后重试。")


def parse_file(path: Path) -> ParsedDocument:
    if path.suffix.lower() in {".txt", ".md"}:
        text = decode_document_text(path.read_bytes()).strip()
        return ParsedDocument((DocumentBlock(text=text),)) if text else ParsedDocument(())
    parsed = parse_document(path)
    if parsed.blocks or path.suffix.lower() != ".pdf":
        return parsed
    # Preserve the application's existing fallback for entirely empty PDF output.
    import fitz

    with fitz.open(path) as pdf:
        blocks = tuple(
            DocumentBlock(text=text, page=index, extra={"adapter_fallback": "empty_parser_blocks"})
            for index, page in enumerate(pdf, start=1)
            if (text := page.get_text("text", sort=True).strip())
        )
    return ParsedDocument(blocks=blocks, images=parsed.images)


class TextOffsets:
    """Convert Python character boundaries without repeatedly encoding prefixes."""

    def __init__(self, text: str):
        self.wide = [index for index, character in enumerate(text) if ord(character) > 0xFFFF]

    def utf16(self, index: int) -> int:
        return index + bisect_left(self.wide, index)


@dataclass(frozen=True)
class ChunkWindow:
    content: str
    ranges: list[dict]


@dataclass(frozen=True)
class DocumentText:
    parsed: ParsedDocument
    blocks: list[dict]
    windows: list[ChunkWindow]
    digest: str

    def locations(self, chunks: list[Chunk]) -> dict[str, list[dict]]:
        result = {}
        by_range = {
            tuple((item["block_id"], item["start"], item["end"]) for item in window.ranges): window
            for window in self.windows
        }
        for chunk in chunks:
            locator = chunk.extra.get("source_locator")
            if isinstance(locator, dict) and locator.get("version") == 1 and locator.get("document_hash") == self.digest:
                saved = locator.get("ranges")
                valid = isinstance(saved, list) and all(
                    isinstance(item, dict)
                    and isinstance(item.get("block_id"), str)
                    and type(item.get("start")) is int
                    and type(item.get("end")) is int
                    for item in saved
                )
                if valid:
                    window = by_range.get(tuple((item["block_id"], item["start"], item["end"]) for item in saved))
                    if window and chunk.source_type == "document" and chunk.content == window.content:
                        result[chunk.chunk_id] = window.ranges
                        continue
            match = _DOCUMENT_SEQUENCE.search(chunk.chunk_id)
            index = int(match[1]) if match else -1
            ranges = []
            if chunk.source_type == "document" and 0 <= index < len(self.windows):
                window = self.windows[index]
                if chunk.content == window.content:
                    ranges = window.ranges
            result[chunk.chunk_id] = ranges
        return result

    def annotate(self, chunks: list[Chunk]) -> list[Chunk]:
        locations = self.locations(chunks)
        return [
            replace(chunk, extra={
                **dict(chunk.extra),
                "source_locator": {"version": 1, "document_hash": self.digest, "ranges": locations[chunk.chunk_id]},
            })
            for chunk in chunks
        ]


def document_text(parsed: ParsedDocument, file_type: str, full_text: str | None = None) -> DocumentText:
    blocks, windows = [], []
    heading_id, previous_heading = None, None
    for index, block in enumerate(parsed.blocks):
        text = block.text.strip()
        heading = block.heading.strip() if block.heading else None
        if heading and heading != previous_heading:
            heading_id = f"heading-{index}"
            blocks.append({"id": heading_id, "kind": "heading", "text": heading, "page": block.page})
        if not heading:
            heading_id = None
        previous_heading = heading
        body_text = full_text if full_text is not None else text
        prefix = len(body_text) - len(body_text.lstrip()) if full_text is not None else 0
        kind = "paragraph"
        if file_type in {"md", "txt"}:
            kind = "markdown" if file_type == "md" else "text"
        elif block.extra.get("block_type") == "table":
            kind = "table"
        block_id = f"block-{index}"
        blocks.append({"id": block_id, "kind": kind, "text": body_text, "page": block.page})
        offsets = TextOffsets(body_text)
        starts = [0] if len(text) <= DOCUMENT_MAX_CHARS else range(0, len(text), DOCUMENT_MAX_CHARS - DOCUMENT_OVERLAP_CHARS)
        for piece_index, start in enumerate(starts):
            end = min(start + DOCUMENT_MAX_CHARS, len(text))
            content = text[start:end]
            ranges = []
            if heading and piece_index == 0:
                content = f"{heading}\n{content}"
                ranges.append({"block_id": heading_id, "start": 0, "end": TextOffsets(heading).utf16(len(heading))})
            ranges.append({"block_id": block_id, "start": offsets.utf16(prefix + start), "end": offsets.utf16(prefix + end)})
            windows.append(ChunkWindow(content=content, ranges=ranges))
    digest = hashlib.sha256(json.dumps(blocks, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return DocumentText(parsed=parsed, blocks=blocks, windows=windows, digest=digest)


def read_document(path: Path) -> DocumentText:
    file_type = path.suffix.lower().lstrip(".")
    parsed = parse_file(path)
    full_text = decode_document_text(path.read_bytes()) if file_type in {"txt", "md"} else None
    return document_text(parsed, file_type, full_text)


def read_document_bytes(data: bytes, file_type: str) -> DocumentText:
    with TemporaryDirectory(prefix="mmrag-source-") as directory:
        path = Path(directory) / f"source.{file_type}"
        path.write_bytes(data)
        return read_document(path)
