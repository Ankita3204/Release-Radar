"""Strict request/response models (extra="forbid" on every input)."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AlertChannelIn(StrictIn):
    kind: Literal["slack", "discord"]
    url: str = Field(min_length=20, max_length=300)


class AlertChannelOut(BaseModel):
    id: UUID
    kind: str
    url_last4: str
    created_at: datetime


class BuildOut(BaseModel):
    id: UUID
    repo: str
    kind: str
    workflow: str | None
    branch: str | None
    head_sha: str | None
    status: str
    conclusion: str | None
    html_url: str | None
    updated_at: datetime


class MeOut(BaseModel):
    login: str
    avatar_url: str | None
    role: str
    csrf_token: str


class DoraOut(BaseModel):
    window_days: int
    deployments: int
    deployment_frequency_per_day: float | None
    change_failure_rate: float | None
    mttr_seconds: float | None
