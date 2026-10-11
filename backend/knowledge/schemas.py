"""HTTP request and response models for the knowledge domain."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.core.schemas import APIModel
from backend.knowledge.models import Visibility
from backend.upload.models import DocumentFormat, ParseStatus


class KBCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    topic_tags: list[str] | None = None


class KBUpdate(BaseModel):
    """改库（部分更新）：只改传入的字段；端点校验至少传一项。"""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    topic_tags: list[str] | None = None


class KBOut(APIModel):
    """知识库视图（含文档数，便于列表展示）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    topic_tags: list | None = None
    visibility: Visibility
    created_at: datetime


class AddDocToKBRequest(BaseModel):
    """把文档归入知识库。"""

    file_id: int
    enabled: bool = True


class KBDocumentUpdate(BaseModel):
    """更新检索启用状态或记录内容反馈。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    # 标记一次用户纠错：只增加 correction_count，不更改 enabled。
    report_correction: bool = False


class KBDocumentOut(APIModel):
    """库内文档视图：含文档本身的关键字段 + enabled 开关。"""

    model_config = ConfigDict(from_attributes=True)

    file_id: int
    file_name: str
    file_type: DocumentFormat
    status: ParseStatus
    enabled: bool
    upload_time: datetime
    meta: dict | None = None
    file_size: int = 0
