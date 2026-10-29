"""Async engine/session helpers and tenant context.

Every request-scoped session runs inside a transaction that first sets
`app.current_org`. On PostgreSQL the RLS policies (see migrations) compare
`org_id` against that setting, so a forgotten WHERE clause in application
code still cannot read another tenant's rows (defence in depth).
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=5) if not url.startswith("sqlite") \
        else create_async_engine(url)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def tenant_session(factory: async_sessionmaker[AsyncSession], org_id: UUID) -> AsyncIterator[AsyncSession]:
    async with factory() as session, session.begin():
        if session.bind.dialect.name == "postgresql":
            await session.execute(text("SELECT set_config('app.current_org', :org, true)"), {"org": str(org_id)})
        yield session
