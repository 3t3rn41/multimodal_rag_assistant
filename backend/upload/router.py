"""Upload, file access, reparsing and owned chunk previews."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.auth.models import User
from backend.infrastructure.database.session import get_session
from backend.upload.fetcher import FetchError, FetchTooLargeError, SSRFError
from backend.upload.schemas import (
    ChunkOut,
    ChunkSourceOut,
    DocumentOut,
    DocumentStatusOut,
    URLUploadRequest,
)
from backend.upload.service import UploadService
from backend.upload.models import DocumentFormat

files_router = APIRouter(prefix="/files", tags=["documents"])
references_router = APIRouter(tags=["document pipeline"])
CurrentUser = Annotated[User, Depends(get_current_user)]
Database = Annotated[AsyncSession, Depends(get_session)]


@files_router.post(
    "/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED
)
async def upload(
    file: UploadFile = File(...),
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """上传文档 -> 存 MinIO + 写 DB + 投递 Celery 任务，返回 pending 状态的 Document。"""
    return await UploadService(session).upload_document(file, current.id)


@files_router.post(
    "/upload_url", response_model=DocumentOut, status_code=status.HTTP_201_CREATED
)
async def upload_url(
    body: URLUploadRequest,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """从 URL 入库：支持 arXiv / PDF 链接。含 SSRF 防护。"""
    try:
        doc = await UploadService(session).upload_from_url(body.url, current.id)
    except SSRFError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"SSRF 拦截：{e}") from e
    except FetchTooLargeError as e:
        raise HTTPException(413, str(e)) from e
    except FetchError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return doc


@files_router.get("/{doc_id}/status", response_model=DocumentStatusOut)
async def get_status(
    doc_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """前端轮询解析进度：pending -> parsing -> done | failed。"""
    return await UploadService(session).owned_document(doc_id, current.id)


@files_router.get("/{doc_id}/content", response_class=Response)
async def original_content(doc_id: int, current: CurrentUser, db: Database):
    doc, content = await UploadService(db).original_content(doc_id, current.id)
    content_types = {
        DocumentFormat.PDF: "application/pdf",
        DocumentFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        DocumentFormat.TXT: "text/plain",
        DocumentFormat.MD: "text/markdown",
    }
    return Response(content,
                    headers={"Content-Disposition": "inline; filename*=UTF-8''" + quote(doc.file_name, safe=""),
                             "Content-Type": content_types.get(doc.file_type, "application/octet-stream"),
                             "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@references_router.post("/files/{doc_id}/reparse", response_model=DocumentStatusOut)
async def reparse(doc_id: int, current: CurrentUser, db: Database):
    return await UploadService(db).reparse(doc_id, current.id)


@references_router.get("/files/{doc_id}/chunks", response_model=list[ChunkOut])
async def list_chunks(doc_id: int, current: CurrentUser, db: Database):
    return await UploadService(db).chunks(doc_id, current.id)


@references_router.get("/chunks/{id}", response_model=ChunkOut)
async def preview_chunk(id: str, current: CurrentUser, db: Database):
    return await UploadService(db).preview_chunk(id, current.id)


@references_router.get("/chunks/{id}/source", response_model=ChunkSourceOut)
async def source_chunk(id: str, current: CurrentUser, db: Database, response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return await UploadService(db).source_chunk(id, current.id)


router = APIRouter()
router.include_router(files_router)
router.include_router(references_router)
