"""Background tasks: ingest normalized events, fan out failure alerts."""
import asyncio
from typing import Any
from uuid import UUID

import httpx
from celery import shared_task
from sqlalchemy import select

from app.core.config import get_settings
from app.core.crypto import DecryptionError, KeyRing
from app.core.logging import configure_logging, get_logger
from app.db.session import make_engine, make_session_factory, tenant_session
from app.models.tables import AlertChannel, BuildEvent, Repository
from app.repositories.tenant import AlertChannelRepository
from app.services.alerts.senders import failure_payload, send
from app.services.events import NormalizedBuild, ingest

log = get_logger()


async def run_ingest_and_alert(factory, keyring: KeyRing, build: dict[str, Any], delivery_id: str,
                               http: httpx.AsyncClient | None = None) -> None:
    result = await ingest(factory, NormalizedBuild(**build), delivery_id)
    if result is None:
        log.info("event_for_unknown_installation", delivery=delivery_id)
        return
    if result.should_alert:
        await alert_for_build(factory, keyring, result.org_id, result.build_id, http)


async def alert_for_build(factory, keyring: KeyRing, org_id: UUID, build_id: UUID, http: httpx.AsyncClient | None = None) -> None:
    async with tenant_session(factory, org_id) as db:
        row = await db.scalar(select(BuildEvent).where(BuildEvent.org_id == org_id, BuildEvent.id == build_id))
        if row is None:
            return
        repo = await db.scalar(select(Repository.full_name).where(Repository.org_id == org_id, Repository.id == row.repo_id))
        channels: list[AlertChannel] = await AlertChannelRepository(db, org_id).list()
    what = "Deployment" if row.kind == "deploy" else "Build"
    for ch in channels:
        try:
            url = keyring.decrypt(ch.url_ciphertext, aad=f"alertchannel:{org_id}:{ch.id}")
        except DecryptionError:
            log.error("alert_channel_undecryptable", channel=str(ch.id))
            continue
        payload = failure_payload(ch.kind, repo=repo or "unknown", workflow=row.workflow_name, branch=row.branch,
                                  conclusion=row.conclusion, url=row.html_url, what=what)
        await send(ch.kind, url, payload, client=http)


@shared_task(name="releaseradar.process_build_event", bind=True, autoretry_for=(OSError,), retry_backoff=True,
             retry_kwargs={"max_retries": 3})
def process_build_event(self, build: dict[str, Any], delivery_id: str) -> None:  # noqa: ARG001
    settings = get_settings()
    configure_logging(settings.env)

    async def _run() -> None:
        engine = make_engine(settings.database_url.get_secret_value())  # new loop per task -> new engine
        try:
            keyring = KeyRing(settings.encryption_keys.get_secret_value(), settings.encryption_current_key_id)
            await run_ingest_and_alert(make_session_factory(engine), keyring, build, delivery_id)
        finally:
            await engine.dispose()

    asyncio.run(_run())
