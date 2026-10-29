"""Application factory. Everything external (Redis, DB, HTTP, queue) is injectable for tests."""
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI
from redis.asyncio import Redis

from app.api.v1.routes import auth, data
from app.core.config import Settings, get_settings
from app.core.crypto import KeyRing
from app.core.logging import configure_logging
from app.db.session import make_engine, make_session_factory
from app.ingress import github_webhook
from app.middleware.errors import install_error_handlers
from app.middleware.http import BodyLimitMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware


def _default_enqueue(settings: Settings) -> Callable[[dict[str, Any], str], None]:
    def enqueue(build: dict[str, Any], delivery_id: str) -> None:
        from app.workers.celery_app import make_celery
        from app.workers.tasks.events import process_build_event

        make_celery(settings)
        process_build_event.delay(build, delivery_id)

    return enqueue


def create_app(
    settings: Settings | None = None, *, redis: Redis | None = None, http_client: httpx.AsyncClient | None = None,
    session_factory: Any = None, enqueue: Callable[[dict[str, Any], str], None] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.env)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = None
        if session_factory is None:
            engine = make_engine(settings.database_url.get_secret_value())
        app.state.session_factory = session_factory or make_session_factory(engine)
        app.state.redis = redis or Redis.from_url(settings.redis_url.get_secret_value(), decode_responses=True)
        app.state.http = http_client or httpx.AsyncClient(follow_redirects=False, timeout=httpx.Timeout(8.0, connect=4.0))
        yield
        if http_client is None:
            await app.state.http.aclose()
        if redis is None:
            await app.state.redis.aclose()
        if engine is not None:
            await engine.dispose()

    docs = {} if settings.docs_enabled else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="ReleaseRadar API", lifespan=lifespan, **docs)
    app.state.settings = settings
    app.state.keyring = KeyRing(settings.encryption_keys.get_secret_value(), settings.encryption_current_key_id)
    app.state.enqueue = enqueue or _default_enqueue(settings)

    # No CORS middleware on purpose: browsers reach this API only through the Next.js
    # same-origin proxy, so there is no cross-origin browser caller to allow.
    # Order matters: the last added runs first (outermost).
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_prod)
    app.add_middleware(BodyLimitMiddleware, default_limit=settings.api_max_body_bytes,
                       path_limits={"/webhooks/github": settings.webhook_max_body_bytes})
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)

    app.include_router(github_webhook.router)
    app.include_router(auth.router)
    app.include_router(data.router)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}  # liveness only: no version, no dependency details

    return app
