from __future__ import with_statement

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import settings
from models.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata


def alembic_include_object(object_, name, type_, reflected, compare_to):
    if type_ == "table" and name in ("users", "sessions", "oidc_states"):
        return False
    return True


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        include_object=alembic_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=alembic_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    # Ensure the URL is suitable for SQLAlchemy's async engine. If the configured
    # URL uses the 'postgresql://' scheme, prefer the asyncpg dialect so the
    # async engine can load an async driver. Do not modify other schemes.
    raw_url = config.get_main_option("sqlalchemy.url") or ""
    if raw_url.startswith("postgresql://") and "+asyncpg" not in raw_url:
        async_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        async_url = raw_url

    connect_args = {}
    # For asyncpg behind pgbouncer, prepared statements can cause errors;
    # setting statement_cache_size=0 disables prepared statement caching.
    if async_url.startswith("postgresql+asyncpg://"):
        connect_args = {"statement_cache_size": 0}

    connectable = create_async_engine(
        async_url,
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations():
    if context.is_offline_mode():
        run_migrations_offline()
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(run_migrations_online())
        return

    loop.run_until_complete(run_migrations_online())


run_migrations()
