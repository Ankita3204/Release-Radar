"""Fixed, read-only tool registry for the assistant (OWASP LLM06: excessive agency).

There is deliberately no tool that writes, re-runs a workflow, rolls back, or
sends a message. Adding one requires an explicit human-confirmation step and a
security review (CODEOWNERS covers this directory).
"""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.tenant import BuildRepository
from app.services.dora import compute_dora


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecentFailuresArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=10, ge=1, le=25)


class DoraArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(default=30, ge=1, le=90)


@dataclass(frozen=True)
class Tool:
    args: type[BaseModel]
    run: Callable[[BaseModel], Awaitable[Any]]


def build_registry(db: AsyncSession, org_id: UUID) -> dict[str, Tool]:
    repo = BuildRepository(db, org_id)

    async def recent_failures(a: BaseModel) -> list[dict[str, Any]]:
        assert isinstance(a, RecentFailuresArgs)
        rows = await repo.list_recent(100)
        failed = [(b, n) for b, n in rows if b.conclusion in {"failure", "timed_out", "startup_failure"}][: a.limit]
        return [{"repo": n, "workflow": b.workflow_name, "branch": b.branch, "conclusion": b.conclusion} for b, n in failed]

    async def dora(a: BaseModel) -> dict[str, Any]:
        assert isinstance(a, DoraArgs)
        now = datetime.now(UTC)
        return compute_dora(await repo.since(now - timedelta(days=a.days)), now=now, window_days=a.days).__dict__

    return {"recent_failures": Tool(RecentFailuresArgs, recent_failures), "dora_metrics": Tool(DoraArgs, dora)}


async def call_tool(registry: dict[str, Tool], name: str, raw_args: dict[str, Any]) -> Any:
    tool = registry.get(name)
    if tool is None:
        raise PermissionError("tool not allowed")
    return await tool.run(tool.args.model_validate(raw_args))  # model-chosen args are validated like user input
