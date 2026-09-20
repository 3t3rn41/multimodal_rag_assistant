"""Member B's dependency-light multimodal ingestion primitives."""

from .chunking import chunk_document, chunk_media, image_chunk
from .embedding import (
    EmbeddingProvider,
    QdrantVectorWriter,
    VectorWriter,
    embed_and_upsert,
    embed_chunks,
)
from .types import DocumentBlock, FrameDescription, TranscriptSegment

__all__ = [
    "DocumentBlock",
    "EmbeddingProvider",
    "FrameDescription",
    "QdrantVectorWriter",
    "TranscriptSegment",
    "VectorWriter",
    "chunk_document",
    "chunk_media",
    "embed_and_upsert",
    "embed_chunks",
    "image_chunk",
]
