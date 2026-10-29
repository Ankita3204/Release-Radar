"""Read/write routes for the dashboard. Authorization = session (org + role) only."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import tenant_db
from app.core.crypto import KeyRing
from app.core.rate_limit import client_ip
from app.core.security import SessionData, require_csrf, require_role
from app.models.tables import AlertChannel
from app.repositories.tenant import AlertChannelRepository, AuditRepository, BuildRepository
from app.schemas.api import AlertChannelIn, AlertChannelOut, BuildOut, DoraOut
from app.services.alerts.ssrf import DestinationRejected, validate_destination
from app.services.dora import compute_dora

router = APIRouter(prefix="/v1")
any_role = require_role("owner", "admin", "viewer")
admin_role = require_role("owner", "admin")


@router.get("/builds", response_model=list[BuildOut])
async def list_builds(limit: int = Query(50, ge=1, le=200), s: SessionData = Depends(any_role),
                      db: AsyncSession = Depends(tenant_db)) -> list[BuildOut]:
    rows = await BuildRepository(db, s.org_id).list_recent(limit)
    return [BuildOut(id=b.id, repo=name, kind=b.kind, workflow=b.workflow_name, branch=b.branch, head_sha=b.head_sha,
                     status=b.status, conclusion=b.conclusion, html_url=b.html_url, updated_at=b.event_ts)
            for b, name in rows]


@router.get("/metrics/dora", response_model=DoraOut)
async def dora(days: int = Query(30, ge=1, le=90), s: SessionData = Depends(any_role),
               db: AsyncSession = Depends(tenant_db)) -> DoraOut:
    now = datetime.now(UTC)
    from datetime import timedelta
    events = await BuildRepository(db, s.org_id).since(now - timedelta(days=days))
    m = compute_dora(events, now=now, window_days=days)
    return DoraOut(**m.__dict__)


@router.get("/alerts", response_model=list[AlertChannelOut])
async def list_alerts(s: SessionData = Depends(admin_role), db: AsyncSession = Depends(tenant_db)) -> list[AlertChannelOut]:
    return [AlertChannelOut(id=c.id, kind=c.kind, url_last4=c.url_last4, created_at=c.created_at)
            for c in await AlertChannelRepository(db, s.org_id).list()]


@router.post("/alerts", response_model=AlertChannelOut, status_code=201, dependencies=[Depends(require_csrf)])
async def create_alert(body: AlertChannelIn, request: Request, s: SessionData = Depends(admin_role),
                       db: AsyncSession = Depends(tenant_db)) -> AlertChannelOut:
    try:
        await validate_destination(body.kind, body.url)
    except DestinationRejected as exc:
        raise HTTPException(status_code=422, detail="destination_rejected") from exc
    keyring: KeyRing = request.app.state.keyring
    channel_id = uuid4()
    channel = AlertChannel(
        id=channel_id, org_id=s.org_id, kind=body.kind, created_by=s.user_id, url_last4=body.url[-4:],
        url_ciphertext=keyring.encrypt(body.url, aad=f"alertchannel:{s.org_id}:{channel_id}"),
    )
    await AlertChannelRepository(db, s.org_id).add(channel)
    await AuditRepository(db, s.org_id).append(actor=s.user_id, action="alert_channel.created",
                                               detail=f"kind={body.kind}", ip=client_ip(request))
    return AlertChannelOut(id=channel.id, kind=channel.kind, url_last4=channel.url_last4,
                           created_at=channel.created_at or datetime.now(UTC))


@router.delete("/alerts/{channel_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_alert(channel_id: UUID, request: Request, s: SessionData = Depends(admin_role),
                       db: AsyncSession = Depends(tenant_db)) -> Response:
    if not await AlertChannelRepository(db, s.org_id).delete(channel_id):
        raise HTTPException(status_code=404, detail="not_found")  # same answer for "missing" and "someone else's"
    await AuditRepository(db, s.org_id).append(actor=s.user_id, action="alert_channel.deleted",
                                               detail=str(channel_id), ip=client_ip(request))
    return Response(status_code=204)
