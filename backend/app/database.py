from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings


class Base(AsyncAttrs, DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


def create_worker_session_factory() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create an engine owned by one RQ coroutine/event loop.

    RQ jobs are synchronous entry points and each one uses ``asyncio.run()``, so
    pooled asyncpg connections must never survive and cross into the next loop.
    """
    worker_engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(
        worker_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    return worker_engine, session_factory


@asynccontextmanager
async def worker_db_session() -> AsyncIterator[AsyncSession]:
    worker_engine, session_factory = create_worker_session_factory()
    try:
        async with session_factory() as session:
            yield session
    finally:
        await worker_engine.dispose()
