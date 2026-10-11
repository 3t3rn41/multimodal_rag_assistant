"""Knowledge-base HTTP contracts; business rules live in KnowledgeService."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.auth.models import User
from backend.infrastructure.database.session import get_session
from backend.knowledge.schemas import (
    AddDocToKBRequest,
    KBCreate,
    KBDocumentOut,
    KBDocumentUpdate,
    KBOut,
    KBUpdate,
)
from backend.knowledge.service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge-base"])


@router.post("", response_model=KBOut, status_code=status.HTTP_201_CREATED)
async def create_kb(
    body: KBCreate,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await KnowledgeService(session).create(current.id, body.model_dump())


@router.get("", response_model=list[KBOut])
async def list_kbs(
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await KnowledgeService(session).list(current.id)


@router.get("/{kb_id}", response_model=KBOut)
async def get_kb(
    kb_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await KnowledgeService(session).owned(kb_id, current.id)


@router.patch("/{kb_id}", response_model=KBOut)
async def update_kb(
    kb_id: int,
    body: KBUpdate,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await KnowledgeService(session).update(
        kb_id, current.id, body.model_dump(exclude_unset=True)
    )


@router.post(
    "/{kb_id}/files", response_model=KBDocumentOut, status_code=status.HTTP_201_CREATED
)
async def add_document(
    kb_id: int,
    body: AddDocToKBRequest,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await KnowledgeService(session).add_file(
        kb_id, current.id, body.file_id, body.enabled
    )


@router.get("/{kb_id}/files", response_model=list[KBDocumentOut])
async def list_documents(
    kb_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await KnowledgeService(session).list_files(kb_id, current.id)


@router.patch("/{kb_id}/files/{doc_id}", response_model=KBDocumentOut)
async def update_kb_document(
    kb_id: int,
    doc_id: int,
    body: KBDocumentUpdate,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await KnowledgeService(session).update_file(
        kb_id, doc_id, current.id, body.enabled, body.report_correction
    )


@router.delete("/{kb_id}/files/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_document(
    kb_id: int,
    doc_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await KnowledgeService(session).remove_file(kb_id, doc_id, current.id)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb(
    kb_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await KnowledgeService(session).delete(kb_id, current.id)
