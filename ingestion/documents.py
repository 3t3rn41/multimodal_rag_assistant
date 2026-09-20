"""Dependency-light document parsing adapters for member B's pipeline."""

from __future__ import annotations

import re
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from xml.etree import ElementTree

from .types import DocumentBlock

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


@dataclass(frozen=True, slots=True)
class ExtractedImage:
    """An image extracted from a document before object-storage upload."""

    data: bytes
    extension: str
    name: str
    page: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Normalized document output consumed by ``chunk_document``."""

    blocks: tuple[DocumentBlock, ...]
    images: tuple[ExtractedImage, ...] = ()


class DocumentParser(Protocol):
    def parse(self, path: Path) -> ParsedDocument: ...


class PyMuPDFParser:
    """Extract text blocks and embedded images with optional PyMuPDF."""

    def __init__(self, *, open_document: Callable[[str], Any] | None = None) -> None:
        self.open_document = open_document

    def parse(self, path: Path) -> ParsedDocument:
        opener = self.open_document or _default_pdf_opener
        document = opener(str(path))
        page_blocks: list[list[str]] = []
        images: list[ExtractedImage] = []
        seen_xrefs: set[int] = set()
        try:
            for page_number, page in enumerate(document, start=1):
                blocks = _pdf_text_blocks(page)
                page_blocks.append(blocks)
                for image_index, image_info in enumerate(
                    page.get_images(full=True),
                    start=1,
                ):
                    xref = int(image_info[0])
                    if xref in seen_xrefs:
                        continue
                    extracted = document.extract_image(xref)
                    data = extracted.get("image")
                    extension = str(extracted.get("ext", "bin"))
                    if not isinstance(data, bytes):
                        continue
                    seen_xrefs.add(xref)
                    images.append(
                        ExtractedImage(
                            data=data,
                            extension=extension,
                            name=f"{path.stem}-p{page_number}-{image_index}.{extension}",
                            page=page_number,
                        )
                    )
            cleaned_pages = remove_repeated_edge_blocks(page_blocks)
            blocks = tuple(
                DocumentBlock(
                    text=text,
                    page=page_number,
                    extra={"block_type": "text", "block_index": block_index},
                )
                for page_number, page in enumerate(cleaned_pages, start=1)
                for block_index, text in enumerate(page)
            )
            return ParsedDocument(blocks=blocks, images=tuple(images))
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                close()


class DocxParser:
    """Parse paragraphs, headings, tables, and embedded images from DOCX XML."""

    def parse(self, path: Path) -> ParsedDocument:
        with zipfile.ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
            blocks: list[DocumentBlock] = []
            heading: str | None = None
            body = root.find(f"{W}body")
            if body is None:
                return ParsedDocument(())
            for element in body:
                if element.tag == f"{W}p":
                    text = _paragraph_text(element)
                    style = _paragraph_style(element)
                    if not text:
                        continue
                    if style.startswith(("Heading", "Title")):
                        heading = text
                        continue
                    blocks.append(
                        DocumentBlock(
                            text=text,
                            heading=heading,
                            extra={"block_type": "paragraph", "style": style},
                        )
                    )
                elif element.tag == f"{W}tbl":
                    table = _table_markdown(element)
                    if table:
                        blocks.append(
                            DocumentBlock(
                                text=table,
                                heading=heading,
                                extra={"block_type": "table"},
                            )
                        )
            images = tuple(
                ExtractedImage(
                    data=archive.read(name),
                    extension=Path(name).suffix.lstrip(".") or "bin",
                    name=Path(name).name,
                )
                for name in archive.namelist()
                if name.startswith("word/media/") and not name.endswith("/")
            )
            return ParsedDocument(blocks=tuple(blocks), images=images)


def parse_document(
    path: Path,
    *,
    pdf_parser: DocumentParser | None = None,
    docx_parser: DocumentParser | None = None,
) -> ParsedDocument:
    """Dispatch PDF/DOCX parsing without importing optional libraries eagerly."""

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return (pdf_parser or PyMuPDFParser()).parse(path)
    if suffix == ".docx":
        return (docx_parser or DocxParser()).parse(path)
    raise ValueError(f"unsupported document type: {path.suffix or '<none>'}")


def remove_repeated_edge_blocks(
    pages: Iterable[Iterable[str]],
    *,
    minimum_occurrences: int = 2,
) -> list[list[str]]:
    """Remove repeated first/last blocks, a conservative header/footer filter."""

    normalized_pages = [[text.strip() for text in page if text.strip()] for page in pages]
    edge_values = [
        _normalize_edge(page[index])
        for page in normalized_pages
        for index in (0, -1)
        if page
    ]
    counts = Counter(edge_values)
    repeated = {
        value for value, count in counts.items() if count >= minimum_occurrences
    }
    cleaned: list[list[str]] = []
    for page in normalized_pages:
        result = list(page)
        while result and _normalize_edge(result[0]) in repeated:
            result.pop(0)
        while result and _normalize_edge(result[-1]) in repeated:
            result.pop()
        cleaned.append(result)
    return cleaned


def _default_pdf_opener(path: str) -> Any:
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("PDF parsing requires the 'documents' optional dependency") from exc
    return fitz.open(path)


def _pdf_text_blocks(page: Any) -> list[str]:
    blocks: list[tuple[float, float, str]] = []
    for raw in page.get_text("blocks"):
        if len(raw) < 5:
            continue
        block_type = raw[6] if len(raw) > 6 else 0
        if block_type != 0:
            continue
        text = str(raw[4]).strip()
        if text:
            blocks.append((float(raw[1]), float(raw[0]), text))
    blocks.sort(key=lambda item: (item[0], item[1]))
    return [text for _, _, text in blocks]


def _normalize_edge(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _paragraph_text(element: ElementTree.Element) -> str:
    return "".join(node.text or "" for node in element.iter(f"{W}t")).strip()


def _paragraph_style(element: ElementTree.Element) -> str:
    style = element.find(f"{W}pPr/{W}pStyle")
    return "" if style is None else str(style.attrib.get(f"{W}val", ""))


def _table_markdown(table: ElementTree.Element) -> str:
    rows: list[list[str]] = []
    for row in table.findall(f"{W}tr"):
        cells = []
        for cell in row.findall(f"{W}tc"):
            value = _paragraph_text(cell).replace("|", "\\|")
            cells.append(value)
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    lines = [
        "| " + " | ".join(normalized[0]) + " |",
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in normalized[1:])
    return "\n".join(lines)
