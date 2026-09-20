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
    MediaAPIConfig,
    VideoIngestionPipeline,
    ingest_audio,
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
    "ParsedDocument",
    "PyMuPDFParser",
    "QdrantVectorWriter",
    "TranscriptSegment",
    "VectorWriter",
    "chunk_document",
    "chunk_media",
    "embed_and_upsert",
    "embed_chunks",
    "image_chunk",
    "index_chunks",
    "ingest_audio",
    "parse_document",
    "VideoIngestionPipeline",
]
