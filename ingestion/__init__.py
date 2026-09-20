"""Member B's dependency-light multimodal ingestion primitives."""

from .chunking import chunk_document, chunk_media, image_chunk
from .api_embeddings import (
    ApiMultimodalEmbedder,
    EmbeddingAPIError,
    MultimodalEmbeddingAPIConfig,
)
from .embedding import (
    ChunkEmbeddingProvider,
    EmbeddingProvider,
    IndexingReport,
    QdrantVectorWriter,
    VectorWriter,
    embed_and_upsert,
    embed_chunks,
    index_chunks,
)
from .types import DocumentBlock, FrameDescription, TranscriptSegment

__all__ = [
    "ApiMultimodalEmbedder",
    "ChunkEmbeddingProvider",
    "DocumentBlock",
    "EmbeddingAPIError",
    "EmbeddingProvider",
    "FrameDescription",
    "IndexingReport",
    "MultimodalEmbeddingAPIConfig",
    "QdrantVectorWriter",
    "TranscriptSegment",
    "VectorWriter",
    "chunk_document",
    "chunk_media",
    "embed_and_upsert",
    "embed_chunks",
    "image_chunk",
    "index_chunks",
]
