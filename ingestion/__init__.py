"""Member B's dependency-light multimodal ingestion primitives."""

from .chunking import chunk_document, chunk_media, image_chunk
from .documents import DocxParser, ExtractedImage, ParsedDocument, PyMuPDFParser, parse_document
from .api_embeddings import (
    ApiMultimodalEmbedder,
    EmbeddingAPIError,
    MultimodalEmbeddingAPIConfig,
)
from .media import (
    ApiImageCaptioner,
    ApiTranscriber,
    FFmpegMediaExtractor,
    FrameSample,
    MediaClipper,
    MediaAPIConfig,
    VideoIngestionPipeline,
    clip_chunk_media,
    ingest_audio,
    is_media_reference,
)
from .embedding import (
    ChunkEmbeddingProvider,
    EmbeddingProvider,
    IndexingReport,
    QdrantVectorWriter,
    VectorWriter,
    ensure_qdrant_collection,
    embed_and_upsert,
    embed_chunks,
    index_chunks,
)
from .types import DocumentBlock, FrameDescription, TranscriptSegment

__all__ = [
    "ApiMultimodalEmbedder",
    "ApiImageCaptioner",
    "ApiTranscriber",
    "ChunkEmbeddingProvider",
    "DocxParser",
    "DocumentBlock",
    "ExtractedImage",
    "FFmpegMediaExtractor",
    "EmbeddingAPIError",
    "EmbeddingProvider",
    "FrameDescription",
    "FrameSample",
    "IndexingReport",
    "MultimodalEmbeddingAPIConfig",
    "MediaAPIConfig",
    "MediaClipper",
    "clip_chunk_media",
    "is_media_reference",
    "ParsedDocument",
    "PyMuPDFParser",
    "QdrantVectorWriter",
    "TranscriptSegment",
    "VectorWriter",
    "chunk_document",
    "chunk_media",
    "embed_and_upsert",
    "embed_chunks",
    "ensure_qdrant_collection",
    "image_chunk",
    "index_chunks",
    "ingest_audio",
    "parse_document",
    "VideoIngestionPipeline",
]
