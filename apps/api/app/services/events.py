"""Parse + ingest GitHub events.

Third-party payloads are untrusted even after the HMAC check passes (anyone
can push a commit message or branch name). We therefore:
  * read ONLY the fields we need, with length bounds and strict patterns;
  * coerce enums to known values;
  * accept html_url only if it points at https://github.com/ (blocks
    javascript:/data: URLs ever reaching an href).
The raw payload never leaves the HTTP handler; workers receive NormalizedBuild.
"""
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import tenant_session
from app.models.tables import Installation
from app.repositories.tenant import BuildRepository, RepoRepository

STATUSES = {"queued", "in_progress", "completed", "requested", "waiting", "pending"}
CONCLUSIONS = {"success", "failure", "cancelled", "skipped", "timed_out", "neutral", "action_required", "stale", "startup_failure"}
FAILURE_CONCLUSIONS = {"failure", "timed_out", "startup_failure"}
SUPPORTED_EVENTS = {"workflow_run", "deployment_status"}


def _clean_url(v: str | None) -> str | None:
    return v if v and v.startswith("https://github.com/") and len(v) <= 500 else None


class _P(BaseModel):
    model_config = ConfigDict(extra="ignore")  # GitHub sends far more than we read; we never touch the rest


class _Repo(_P):
    id: int
    full_name: str = Field(max_length=200, pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
    default_branch: str | None = Field(default=None, max_length=255)


class _Install(_P):
    id: int


class _WorkflowRun(_P):
    id: int
    name: str | None = Field(default=None, max_length=255)
    head_branch: str | None = Field(default=None, max_length=255)
    head_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    status: str | None = None
    conclusion: str | None = None
    html_url: str | None = None
    updated_at: datetime

    _url = field_validator("html_url")(staticmethod(_clean_url))


class _WorkflowRunEvent(_P):
    workflow_run: _WorkflowRun
    repository: _Repo
    installation: _Install


class _Deployment(_P):
    id: int
    sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    ref: str | None = Field(default=None, max_length=255)
    environment: str | None = Field(default=None, max_length=255)


class _DeploymentStatus(_P):
    state: str = Field(max_length=30)
    target_url: str | None = None
    updated_at: datetime | None = None
    created_at: datetime


class _DeploymentStatusEvent(_P):
    deployment: _Deployment
    deployment_status: _DeploymentStatus
    repository: _Repo
    installation: _Install


@dataclass(frozen=True)
class NormalizedBuild:
    kind: str
    run_id: int
    installation_id: int
    repo_github_id: int
    repo_full_name: str
    default_branch: str | None
    workflow_name: str | None
    branch: str | None
    head_sha: str
    status: str
    conclusion: str | None
    html_url: str | None
    event_ts: str  # ISO-8601, JSON-safe for the queue

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_event(event: str, payload: dict[str, Any]) -> NormalizedBuild | None:
    """Returns None for events we do not track. Raises ValidationError for malformed tracked events."""
    if event == "workflow_run":
        e = _WorkflowRunEvent.model_validate(payload)
        r = e.workflow_run
        return NormalizedBuild(
            kind="build", run_id=r.id, installation_id=e.installation.id, repo_github_id=e.repository.id,
            repo_full_name=e.repository.full_name, default_branch=e.repository.default_branch,
            workflow_name=r.name, branch=r.head_branch, head_sha=r.head_sha,
            status=r.status if r.status in STATUSES else "pending",
            conclusion=r.conclusion if r.conclusion in CONCLUSIONS else None,
            html_url=r.html_url, event_ts=_aware(r.updated_at).isoformat(),
        )
    if event == "deployment_status":
        e2 = _DeploymentStatusEvent.model_validate(payload)
        s = e2.deployment_status
        terminal = {"success": "success", "failure": "failure", "error": "failure"}
        conclusion = terminal.get(s.state)
        return NormalizedBuild(
            kind="deploy", run_id=e2.deployment.id, installation_id=e2.installation.id,
            repo_github_id=e2.repository.id, repo_full_name=e2.repository.full_name,
            default_branch=e2.repository.default_branch, workflow_name=e2.deployment.environment,
            branch=e2.deployment.ref, head_sha=e2.deployment.sha,
            status="completed" if conclusion else "in_progress", conclusion=conclusion,
            html_url=_clean_url(s.target_url), event_ts=_aware(s.updated_at or s.created_at).isoformat(),
        )
    return None


@dataclass(frozen=True)
class IngestResult:
    org_id: UUID
    build_id: UUID
    should_alert: bool


async def resolve_org(session: AsyncSession, installation_id: int) -> UUID | None:
    return await session.scalar(select(Installation.org_id).where(Installation.installation_id == installation_id))


async def ingest(factory: async_sessionmaker[AsyncSession], build: NormalizedBuild, delivery_id: str) -> IngestResult | None:
    async with factory() as lookup:
        org_id = await resolve_org(lookup, build.installation_id)
    if org_id is None:
        return None  # unknown installation: ignore rather than guess a tenant
    async with tenant_session(factory, org_id) as session:
        repo = await RepoRepository(session, org_id).upsert(
            github_id=build.repo_github_id, full_name=build.repo_full_name, default_branch=build.default_branch
        )
        row, previous, applied = await BuildRepository(session, org_id).upsert(
            repo_id=repo.id, kind=build.kind, run_id=build.run_id, delivery_id=delivery_id,
            event_ts=datetime.fromisoformat(build.event_ts), workflow_name=build.workflow_name, branch=build.branch,
            head_sha=build.head_sha, status=build.status, conclusion=build.conclusion, html_url=build.html_url,
        )
        # Alert only on the transition INTO failure, so redeliveries/retries never double-notify.
        failed_now = build.conclusion in FAILURE_CONCLUSIONS
        should_alert = applied and failed_now and previous not in FAILURE_CONCLUSIONS
        return IngestResult(org_id, row.id, should_alert)


__all__ = ["NormalizedBuild", "parse_event", "ingest", "IngestResult", "SUPPORTED_EVENTS", "ValidationError"]
