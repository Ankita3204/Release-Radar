from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import SessionData, current_session
from app.db.session import tenant_session


async def tenant_db(request: Request, session: SessionData = Depends(current_session)) -> AsyncIterator[AsyncSession]:
    """One transaction per request, bound to the caller's org (never taken from request input)."""
    async with tenant_session(request.app.state.session_factory, session.org_id) as s:
        yield s
