import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine.url import make_url

from app.config.settings import get_settings
from app.models.base import Base

logger = logging.getLogger(__name__)

# Import every model module so Base.metadata is fully populated for autogenerate.
from app.models import agent_run, audit_log, merchant, order, policy, product  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _normalize_psycopg2_url(url: str) -> str:
    """
    Reverse of app/db/session.py's asyncpg normalization: psycopg2 (which
    Alembic uses for migrations) wants "sslmode", not asyncpg's "ssl" query
    param. Convert defensively via SQLAlchemy's URL object (not hand-rolled
    string concatenation, which would mangle passwords containing
    @ / + = % etc.) so either spelling in DATABASE_URL works here.
    """
    parsed = make_url(url)
    query = dict(parsed.query)

    ssl = query.pop("ssl", None)
    if ssl is not None:
        query["sslmode"] = "disable" if ssl == "disable" else "require"
        logger.warning(
            "DATABASE_URL uses ssl=%s, which psycopg2 doesn't support; "
            "converted to sslmode=%s for migrations.",
            ssl,
            query["sslmode"],
        )

    return parsed.set(query=query).render_as_string(hide_password=False)


def get_sync_db_url() -> str:
    settings = get_settings()
    parsed = make_url(settings.database_url).set(drivername="postgresql+psycopg2")
    return _normalize_psycopg2_url(parsed.render_as_string(hide_password=False))


def run_migrations_offline() -> None:
    url = get_sync_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_sync_db_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
