from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

if settings.APP_ENV == "test":
    # NullPool: every checkout opens a fresh asyncpg connection instead of
    # reusing one from a pool. Pooled asyncpg connections are bound to the
    # event loop that created them, and pytest-asyncio can hand different
    # tests different loops even under loop_scope="session" once sync tests
    # are interleaved — a reused connection then errors with "attached to a
    # different loop". Outside tests we want real pooling for performance,
    # so this only applies under APP_ENV=test.
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, echo=False)
else:
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        echo=False,
    )

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_db_health() -> bool:
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
