"""Shared transaction operations for the application repositories."""

from sqlalchemy.ext.asyncio import AsyncSession


class AsyncRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, row):
        self.db.add(row)
        await self.db.flush()
        return row

    def add(self, row):
        self.db.add(row)

    async def flush(self):
        await self.db.flush()

    async def commit(self):
        await self.db.commit()

    async def rollback(self):
        await self.db.rollback()

    async def refresh(self, row):
        await self.db.refresh(row)

    async def delete(self, row):
        await self.db.delete(row)
