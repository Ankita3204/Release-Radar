import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.base import Base
from app.models import tables  # noqa: F401  (register models)

target_metadata = Base.metadata


def _url() -> str:
    # Migrations run as a SEPARATE owner role (MIGRATION_DATABASE_URL), never as the app's runtime role.
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        raise RuntimeError("MIGRATION_DATABASE_URL is required")
    return url


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _online() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


asyncio.run(_online())
