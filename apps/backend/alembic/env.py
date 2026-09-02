from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config.settings import get_settings
from app.models.base import Base

# Import every model module so Base.metadata is fully populated for autogenerate.
from app.models import agent_run, audit_log, merchant, order, policy, product  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_sync_db_url() -> str:
    settings = get_settings()
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


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
