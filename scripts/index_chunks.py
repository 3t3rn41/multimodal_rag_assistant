"""Resume API embedding and Qdrant indexing from a Chunk JSONL file."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from collections.abc import Callable, Iterable
from pathlib import Path

from ingestion import (
    ApiMultimodalEmbedder,
    MultimodalEmbeddingAPIConfig,
    QdrantVectorWriter,
    ensure_qdrant_collection,
    index_chunks,
)
from ingestion.media import is_media_reference
from rag_engine.models import Chunk


def read_chunks(path: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from exc
            chunks.append(Chunk.from_payload(payload))
    return chunks


def _media_url_resolver(value: str) -> str | None:
    base_url = os.getenv("RAG_MEDIA_PUBLIC_BASE_URL", "").rstrip("/")
    if value.startswith("minio://") and base_url:
        return f"{base_url}/{value.removeprefix('minio://')}"
    if value.startswith(("https://", "http://", "data:")):
        return value
    return None


def validate_media_references(
    chunks: Iterable[Chunk],
    resolver: Callable[[str], str | None],
) -> None:
    """Reject media that the embedding endpoint would silently ignore."""

    for chunk in chunks:
        values: list[str | None] = []
        if chunk.source_type == "image":
            values.append(chunk.media_path)
        elif chunk.source_type in {"audio", "video"}:
            values.append(chunk.extra.get("source_media_path"))
            if chunk.source_type == "video":
                values.append(chunk.media_path)
        for value in values:
            if not value:
                continue
            raw_value = str(value)
            if not is_media_reference(raw_value):
                raise ValueError(
                    f"chunk {chunk.chunk_id!r} has a local media path; "
                    "create a remote media reference and persist minio:// or HTTP(S) first"
                )
            resolved = resolver(raw_value)
            if not resolved or not resolved.startswith(("https://", "http://", "data:")):
                raise ValueError(
                    f"chunk {chunk.chunk_id!r} media reference {raw_value!r} "
                    "does not resolve to an HTTP(S) or data URL"
                )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--qdrant-url", default=os.getenv("RAG_QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--qdrant-api-key", default=os.getenv("RAG_QDRANT_API_KEY", ""))
    parser.add_argument(
        "--qdrant-path",
        type=Path,
        default=(Path(os.environ["RAG_QDRANT_PATH"])
                 if os.getenv("RAG_QDRANT_PATH") else None),
        help="use Qdrant's local persistent mode instead of an HTTP server",
    )
    parser.add_argument(
        "--collection",
        default=os.getenv("RAG_QDRANT_COLLECTION", "jina_v5_omni_small_1024"),
    )
    parser.add_argument("--vector-name", default=os.getenv("RAG_QDRANT_VECTOR_NAME", "dense"))
    parser.add_argument(
        "--embedding-dimensions",
        type=int,
        default=int(os.getenv("RAG_EMBEDDING_DIMENSIONS", "1024")),
    )
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="recreate the named Jina collection before indexing every input chunk",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise SystemExit("install the 'qdrant' optional dependency first") from exc

    chunks = read_chunks(args.chunks)
    validate_media_references(chunks, _media_url_resolver)
    embedding_config = MultimodalEmbeddingAPIConfig.from_env()
    dimensions = embedding_config.dimensions or args.embedding_dimensions
    if dimensions <= 0:
        raise SystemExit("embedding dimensions must be positive")
    provider = ApiMultimodalEmbedder(
        embedding_config,
        media_url_resolver=_media_url_resolver,
    )
    if args.qdrant_path is not None:
        args.qdrant_path.parent.mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=str(args.qdrant_path))
    else:
        client = QdrantClient(
            url=args.qdrant_url,
            api_key=args.qdrant_api_key or None,
        )
    ensure_qdrant_collection(
        client,
        args.collection,
        dimensions,
        vector_name=args.vector_name or None,
        recreate=args.rebuild,
    )
    writer = QdrantVectorWriter(
        client,
        args.collection,
        vector_name=args.vector_name or None,
    )
    report = index_chunks(chunks, provider, writer, batch_size=args.batch_size)
    print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
