"""DORA metrics from real deployment events.

Lead time for changes is intentionally not computed: it needs commit
timestamps, which this scaffold does not ingest yet.
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.models.tables import BuildEvent


@dataclass(frozen=True)
class DoraMetrics:
    window_days: int
    deployments: int
    deployment_frequency_per_day: float | None
    change_failure_rate: float | None
    mttr_seconds: float | None


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def compute_dora(events: list[BuildEvent], *, now: datetime, window_days: int = 30) -> DoraMetrics:
    cutoff = now - timedelta(days=window_days)
    deploys = sorted(
        (e for e in events if e.kind == "deploy" and e.conclusion in {"success", "failure"} and _aware(e.event_ts) >= cutoff),
        key=lambda e: _aware(e.event_ts),
    )
    if not deploys:
        return DoraMetrics(window_days, 0, None, None, None)
    ok = [d for d in deploys if d.conclusion == "success"]
    failed = [d for d in deploys if d.conclusion == "failure"]

    recoveries: list[float] = []
    by_repo: dict[object, list[BuildEvent]] = {}
    for d in deploys:
        by_repo.setdefault(d.repo_id, []).append(d)
    for seq in by_repo.values():
        open_failure: BuildEvent | None = None
        for d in seq:
            if d.conclusion == "failure" and open_failure is None:
                open_failure = d
            elif d.conclusion == "success" and open_failure is not None:
                recoveries.append((_aware(d.event_ts) - _aware(open_failure.event_ts)).total_seconds())
                open_failure = None

    return DoraMetrics(
        window_days=window_days,
        deployments=len(ok),
        deployment_frequency_per_day=len(ok) / window_days,
        change_failure_rate=len(failed) / len(deploys),
        mttr_seconds=(sum(recoveries) / len(recoveries)) if recoveries else None,
    )
