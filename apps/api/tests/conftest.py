import base64
import os
import time
from uuid import uuid4

import fakeredis.aioredis
import httpx
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.security import SESSION_COOKIE, create_session
from app.db.base import Base
from app.db.session import make_session_factory
from app.main import create_app
from app.models import tables as t

WEBHOOK_SECRET = "w" * 40
WEB_ORIGIN = "https://app.test"


def _pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        env="test", database_url="sqlite+aiosqlite://", redis_url="redis://localhost", web_origin=WEB_ORIGIN,
        github_app_id="1", github_client_id="Iv1.test", github_client_secret="cs", github_app_private_key=_pem(),
        github_webhook_secret=WEBHOOK_SECRET,
        encryption_keys="k1:" + base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("="),
        encryption_current_key_id="k1",
    )


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield make_session_factory(engine)
    await engine.dispose()


@pytest_asyncio.fixture
async def redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield r
    await r.aclose()


@pytest.fixture
def enqueued():
    return []


@pytest.fixture
def github_handler():
    """Override in a test to script GitHub's answers."""
    return {"fn": lambda request: httpx.Response(404)}


@pytest_asyncio.fixture
async def client(settings, factory, redis, enqueued, github_handler):
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: github_handler["fn"](r)))
    app = create_app(settings, redis=redis, http_client=http, session_factory=factory,
                     enqueue=lambda build, delivery: enqueued.append((build, delivery)))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://api.test") as c:
            c.app = app
            yield c
    await http.aclose()


async def make_org(factory, *, login="alice", role="owner", installation_id=None):
    async with factory() as s, s.begin():
        org = t.Organization(id=uuid4(), name=f"{login} org")
        user = t.User(id=uuid4(), github_id=int(time.time() * 1000) % 10**9 + hash(login) % 1000, login=login)
        s.add_all([org, user])
        await s.flush()
        s.add(t.Membership(org_id=org.id, user_id=user.id, role=role))
        if installation_id:
            s.add(t.Installation(installation_id=installation_id, org_id=org.id, account_login=login))
    return org.id, user.id


async def login_as(client, redis, settings, org_id, user_id, role="owner"):
    sid, data = await create_session(redis, settings, user_id=user_id, org_id=org_id, role=role)
    client.cookies.set(SESSION_COOKIE, sid)
    return data
