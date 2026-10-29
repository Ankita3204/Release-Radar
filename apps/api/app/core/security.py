"""Server-side sessions, CSRF defence and role checks.

  * Opaque session IDs, not JWTs in the browser. Redis stores session data
    under sha256(id), so a Redis dump does not yield usable cookies.
  * Cookie: __Host- prefix (Secure, Path=/, no Domain), HttpOnly, SameSite=Lax.
  * CSRF: every state-changing request needs (a) Origin == WEB_ORIGIN and
    (b) an X-CSRF-Token bound to the session. SameSite is not the only defence.
  * Idle + absolute timeouts; a new session id is minted on every login.
"""
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from redis.asyncio import Redis

from app.core.config import Settings

SESSION_COOKIE = "__Host-releaseradar_sid"
OAUTH_COOKIE = "__Host-releaseradar_oauth"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ROLES = ("owner", "admin", "viewer")


def _key(sid: str) -> str:
    return "sess:" + hashlib.sha256(sid.encode()).hexdigest()


@dataclass
class SessionData:
    user_id: UUID
    org_id: UUID
    role: str
    csrf: str
    created_at: float

    def dumps(self) -> str:
        return json.dumps(
            {"user_id": str(self.user_id), "org_id": str(self.org_id), "role": self.role,
             "csrf": self.csrf, "created_at": self.created_at}
        )

    @classmethod
    def loads(cls, raw: str) -> "SessionData":
        d = json.loads(raw)
        return cls(UUID(d["user_id"]), UUID(d["org_id"]), d["role"], d["csrf"], float(d["created_at"]))


async def create_session(
    redis: Redis, settings: Settings, *, user_id: UUID, org_id: UUID, role: str
) -> tuple[str, SessionData]:
    sid = secrets.token_urlsafe(32)
    data = SessionData(user_id, org_id, role, secrets.token_urlsafe(32), time.time())
    await redis.set(_key(sid), data.dumps(), ex=settings.session_idle_seconds)
    return sid, data


async def destroy_session(redis: Redis, sid: str) -> None:
    await redis.delete(_key(sid))


async def load_session(redis: Redis, settings: Settings, sid: str | None) -> SessionData | None:
    if not sid or len(sid) > 128:
        return None
    raw = await redis.get(_key(sid))
    if raw is None:
        return None
    data = SessionData.loads(raw)
    if time.time() - data.created_at > settings.session_absolute_seconds:
        await redis.delete(_key(sid))
        return None
    await redis.expire(_key(sid), settings.session_idle_seconds)  # sliding idle timeout
    return data


async def current_session(request: Request) -> SessionData:
    data = await load_session(
        request.app.state.redis, request.app.state.settings, request.cookies.get(SESSION_COOKIE)
    )
    if data is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return data


async def require_csrf(request: Request, session: SessionData = Depends(current_session)) -> None:
    if request.method in SAFE_METHODS:
        return
    if request.headers.get("origin") != request.app.state.settings.web_origin:
        raise HTTPException(status_code=403, detail="bad_origin")
    supplied = request.headers.get("x-csrf-token", "")
    if not hmac.compare_digest(supplied.encode(), session.csrf.encode()):
        raise HTTPException(status_code=403, detail="bad_csrf_token")


def require_role(*allowed: str) -> Callable[..., Awaitable[SessionData]]:
    assert set(allowed) <= set(ROLES)

    async def dependency(session: SessionData = Depends(current_session)) -> SessionData:
        if session.role not in allowed:
            raise HTTPException(status_code=403, detail="forbidden")
        return session

    return dependency
