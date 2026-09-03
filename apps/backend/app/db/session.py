"""Async SQLAlchemy engine, sessionmaker, and the get_db() FastAPI dependency."""
import logging
from collections.abc import AsyncGenerator

from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


def _normalize_asyncpg_url(url: str) -> str:
    """
    asyncpg doesn't understand psycopg2/libpq's "sslmode" query param — it wants
    "ssl" instead, and doesn't understand "channel_binding" at all. Providers
    (e.g. Neon) commonly hand out sslmode=/channel_binding= URLs, so convert
    defensively via SQLAlchemy's URL object rather than hand-rolled string
    concatenation, which would mangle passwords containing @ / + = % etc.
    """
    parsed = make_url(url)
    query = dict(parsed.query)

    query.pop("channel_binding", None)

    sslmode = query.pop("sslmode", None)
    if sslmode is not None:
        query["ssl"] = "disable" if sslmode == "disable" else "require"
        logger.warning(
            "DATABASE_URL uses sslmode=%s, which asyncpg doesn't support; "
            "converted to ssl=%s.",
            sslmode,
            query["ssl"],
        )

    return parsed.set(query=query).render_as_string(hide_password=False)


engine = create_async_engine(
    _normalize_asyncpg_url(settings.database_url),
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
