"""Async SQLAlchemy engine, sessionmaker, and the get_db() FastAPI dependency."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "dev",
    pool_pre_ping=True,
)

async_session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a session, commits on success, rolls back on error."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
