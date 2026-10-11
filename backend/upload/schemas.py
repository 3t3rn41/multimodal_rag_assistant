"""HTTP request and response models for the upload domain."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from backend.core.schemas import APIModel
from backend.upload.models import DocumentFormat, ParseStatus


class DocumentOut(APIModel):
    """文档元信息视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str
    file_type: DocumentFormat
    status: ParseStatus
    version: int
    upload_time: datetime
    meta: dict | None = None
    file_size: int = 0
    storage_path: str

    @computed_field
    @property
    def task_id(self) -> str | None:
        return (self.meta or {}).get("task_id")


class URLUploadRequest(BaseModel):
    """URL 入库请求。支持 arXiv 与 PDF 链接导入。"""

    url: str = Field(min_length=8, max_length=2048)


class DocumentStatusOut(BaseModel):
    """解析状态查询：前端轮询用。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: ParseStatus
    meta: dict | None = None  # 含 chunk_count / error / parser 等


class ChunkOut(APIModel):
    chunk_id: str
    file_id: str
    source_type: str
    content: str
    page: int | None = None
    time_start: float | None = None
    time_end: float | None = None
    media_path: str | None = None
    extra: dict = Field(default_factory=dict)
    file_name: str | None = None
    file_type: str | None = None
    generation: int
    seq: int | None = None
    section_path: list[str] | str | None = None
    preview_url: str | None = None
    pdf_url: str | None = None


class SourceBlockOut(BaseModel):
    id: str
    kind: Literal["heading", "paragraph", "table", "text", "markdown"]
    text: str
    page: int | None = None


class SourceRangeOut(BaseModel):
    block_id: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class ChunkSourceOut(ChunkOut):
    blocks: list[SourceBlockOut]
    locations: dict[str, list[SourceRangeOut]]
    contents: dict[str, str]
    original_url: str
