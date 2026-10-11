"""Knowledge-base ownership and membership business rules."""

from backend.core.errors import ServiceError
from backend.knowledge.models import KBDocument, KnowledgeBase
from backend.knowledge.repository import KnowledgeRepository
from backend.upload.service import UploadService


class KnowledgeService:
    def __init__(self, db):
        self.repo = KnowledgeRepository(db)
        self.files = UploadService(db)

    async def owned(self, kb_id, owner_id, *, lock=False):
        kb = await self.repo.get(kb_id, lock=lock)
        if kb is None or kb.owner_id != owner_id:
            raise ServiceError("知识库不存在", 404)
        return kb

    async def lock_memberships(self, kb_id, owner_id):
        await self.files.repo.lock_owner(owner_id)
        return await self.owned(kb_id, owner_id, lock=True)

    async def create(self, owner_id, values):
        kb = await self.repo.create(KnowledgeBase(owner_id=owner_id, **values))
        await self.repo.commit()
        await self.repo.refresh(kb)
        return kb

    async def list(self, owner_id):
        return await self.repo.list(owner_id)

    async def update(self, kb_id, owner_id, changes):
        kb = await self.owned(kb_id, owner_id)
        if not changes:
            raise ServiceError("请至少传入一个要修改的字段")
        if "name" in changes and changes["name"] is None:
            raise ServiceError("知识库名称不能为空")
        for name, value in changes.items():
            setattr(kb, name, value or None if name == "description" else value)
        await self.repo.commit()
        await self.repo.refresh(kb)
        return kb

    @staticmethod
    def file_view(doc, membership):
        return {
            "file_id": doc.id,
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "status": doc.status,
            "meta": doc.meta,
            "upload_time": doc.upload_time,
            "file_size": doc.file_size,
            "enabled": membership.enabled,
        }

    async def add_file(self, kb_id, owner_id, file_id, enabled):
        await self.lock_memberships(kb_id, owner_id)
        doc = await self.files.owned_document(file_id, owner_id, lock=True)
        if await self.repo.membership(kb_id, file_id, lock=True) is not None:
            raise ServiceError("文档已在该知识库中", 409)
        membership = await self.repo.create(
            KBDocument(kb_id=kb_id, file_id=file_id, enabled=enabled)
        )
        await self.repo.commit()
        return self.file_view(doc, membership)

    async def list_files(self, kb_id, owner_id):
        await self.owned(kb_id, owner_id)
        return [self.file_view(doc, link) for link, doc in await self.repo.files(kb_id)]

    async def owned_membership(self, kb_id, file_id, owner_id):
        await self.owned(kb_id, owner_id)
        link = await self.repo.membership(kb_id, file_id)
        if link is None:
            raise ServiceError("文档不在该知识库中", 404)
        return link

    async def update_file(self, kb_id, file_id, owner_id, enabled, correction):
        link = await self.owned_membership(kb_id, file_id, owner_id)
        doc = await self.files.owned_document(file_id, owner_id)
        if enabled is not None:
            link.enabled = enabled
        if correction:
            link.correction_count = (link.correction_count or 0) + 1
        await self.repo.commit()
        return self.file_view(doc, link)

    async def remove_file(self, kb_id, file_id, owner_id):
        await self.lock_memberships(kb_id, owner_id)
        doc = await self.files.owned_document(file_id, owner_id, lock=True, include_deleted=True)
        link = await self.repo.membership(kb_id, file_id, lock=True)
        if link is None:
            await self.repo.commit()
            return
        await self.repo.delete(link)
        await self.repo.db.flush()
        cleanup = not await self.repo.has_memberships(file_id)
        if cleanup:
            _, tasks = await self.files.prepare_deletion(doc)
        await self.repo.commit()
        if cleanup:
            await self.files.dispatch_cleanup(tasks)

    async def delete(self, kb_id, owner_id):
        kb = await self.lock_memberships(kb_id, owner_id)
        docs = [await self.files.owned_document(file_id, owner_id, lock=True, include_deleted=True)
                for file_id in await self.repo.file_ids(kb_id)]
        await self.repo.remove_knowledge(kb)
        await self.repo.db.flush()
        cleanup_count, tasks = 0, []
        for doc in docs:
            if not await self.repo.has_memberships(doc.id):
                _, cancelled = await self.files.prepare_deletion(doc)
                cleanup_count += 1
                tasks.extend(cancelled)
        await self.repo.commit()
        if cleanup_count:
            await self.files.dispatch_cleanup(tasks)
