"""The ONLY layer that talks to the database for tenant data.

Every repository is constructed with an org_id (no default) and adds
`org_id = :org` to every query. Combined with Postgres RLS this gives two
independent barriers against cross-tenant access (CWE-639 / CWE-862).
"""
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import AlertChannel, AuditLog, BuildEvent, Repository


class TenantRepo:
    def __init__(self, session: AsyncSession, org_id: UUID) -> None:
        if not isinstance(org_id, UUID):
            raise TypeError("org_id must be a UUID")
        self.session = session
        self.org_id = org_id


class RepoRepository(TenantRepo):
    async def list(self) -> list[Repository]:
        res = await self.session.scalars(
            select(Repository).where(Repository.org_id == self.org_id).order_by(Repository.full_name)
        )
        return list(res)

    async def upsert(self, *, github_id: int, full_name: str, default_branch: str | None) -> Repository:
        repo = await self.session.scalar(
            select(Repository).where(Repository.org_id == self.org_id, Repository.github_id == github_id)
        )
        if repo is None:
            repo = Repository(org_id=self.org_id, github_id=github_id, full_name=full_name, default_branch=default_branch)
            self.session.add(repo)
        else:
            repo.full_name, repo.default_branch = full_name, default_branch
        await self.session.flush()
        return repo


class BuildRepository(TenantRepo):
    async def list_recent(self, limit: int = 50) -> list[tuple[BuildEvent, str]]:
        limit = max(1, min(limit, 200))
        rows = await self.session.execute(
            select(BuildEvent, Repository.full_name)
            .join(Repository, Repository.id == BuildEvent.repo_id)
            .where(BuildEvent.org_id == self.org_id)
            .order_by(BuildEvent.event_ts.desc())
            .limit(limit)
        )
        return [(b, name) for b, name in rows.all()]

    async def get(self, build_id: UUID) -> BuildEvent | None:
        return await self.session.scalar(
            select(BuildEvent).where(BuildEvent.org_id == self.org_id, BuildEvent.id == build_id)
        )

    async def since(self, cutoff: datetime) -> list[BuildEvent]:
        res = await self.session.scalars(
            select(BuildEvent).where(BuildEvent.org_id == self.org_id, BuildEvent.event_ts >= cutoff)
        )
        return list(res)

    async def upsert(self, *, repo_id: UUID, kind: str, run_id: int, delivery_id: str, event_ts: datetime,
                     **fields: object) -> tuple[BuildEvent, str | None, bool]:
        """Returns (row, previous_conclusion, applied). Stale (older) events are ignored."""
        row = await self.session.scalar(
            select(BuildEvent).where(
                BuildEvent.org_id == self.org_id, BuildEvent.repo_id == repo_id,
                BuildEvent.kind == kind, BuildEvent.run_id == run_id,
            )
        )
        if row is None:
            row = BuildEvent(org_id=self.org_id, repo_id=repo_id, kind=kind, run_id=run_id,
                             event_ts=event_ts, last_delivery_id=delivery_id, **fields)
            self.session.add(row)
            await self.session.flush()
            return row, None, True
        previous = row.conclusion
        if event_ts < _aware(row.event_ts):
            return row, previous, False
        for k, v in fields.items():
            setattr(row, k, v)
        row.event_ts, row.last_delivery_id = event_ts, delivery_id
        await self.session.flush()
        return row, previous, True


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class AlertChannelRepository(TenantRepo):
    async def list(self) -> list[AlertChannel]:
        res = await self.session.scalars(
            select(AlertChannel).where(AlertChannel.org_id == self.org_id).order_by(AlertChannel.created_at)
        )
        return list(res)

    async def add(self, channel: AlertChannel) -> AlertChannel:
        if channel.org_id != self.org_id:
            raise PermissionError("cross-tenant insert refused")
        self.session.add(channel)
        await self.session.flush()
        return channel

    async def delete(self, channel_id: UUID) -> bool:
        res = await self.session.execute(
            delete(AlertChannel).where(AlertChannel.org_id == self.org_id, AlertChannel.id == channel_id)
        )
        return (res.rowcount or 0) > 0


class AuditRepository(TenantRepo):
    async def append(self, *, actor: UUID | None, action: str, detail: str | None = None, ip: str | None = None) -> None:
        self.session.add(AuditLog(org_id=self.org_id, actor_user_id=actor, action=action, detail=detail, ip=ip))
        await self.session.flush()
