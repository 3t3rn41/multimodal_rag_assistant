"""异步与同步数据库引擎、会话工厂。

设计：
- 异步引擎（asyncmy）：API 进程用。FastAPI 基于事件循环，DB I/O 不能阻塞，用异步驱动。
- 同步引擎（pymysql）：Worker 进程用。Celery Worker 跑 minio（同步）+ 解析器
  （同步 CPU），全链路同步，用同步 DB 驱动与之配套，避免在 worker 里混用 async。
- `async_sessionmaker(expire_on_commit=False)`：commit 后对象属性仍可访问，
  避免在异步上下文里因懒加载触发额外的 I/O（异步下懒加载会直接报错）。
- `get_session()` 是 FastAPI 依赖：每个请求一个 session，正常提交、异常回滚、
  结束必关闭。测试里用 `app.dependency_overrides[get_session]` 换成测试库即可。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import settings

# ---- 异步（API 进程）----
engine: AsyncEngine = create_async_engine(
    settings.build_database_url(driver="asyncmy"),
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：请求级会话，自动提交/回滚/关闭。"""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---- 同步（Worker / 脚本）----
sync_engine = create_engine(
    settings.build_database_url(driver="pymysql"),
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SyncSessionLocal: sessionmaker[Session] = sessionmaker(
    bind=sync_engine,
    expire_on_commit=False,
    autoflush=False,
)
