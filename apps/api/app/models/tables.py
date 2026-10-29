"""ORM models. Every tenant-owned table carries a NOT NULL, indexed org_id."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid_pk() -> Mapped[UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid4)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = _uuid_pk()
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    login: Mapped[str] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id"),
        CheckConstraint("role in ('owner','admin','viewer')", name="ck_membership_role"),
    )
    id: Mapped[UUID] = _uuid_pk()
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))


class Installation(Base):
    """GitHub App installation -> org mapping. Looked up by webhook ingestion, so it is not RLS-scoped."""
    __tablename__ = "installations"
    id: Mapped[UUID] = _uuid_pk()
    installation_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    account_login: Mapped[str] = mapped_column(String(100))


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("org_id", "github_id"),)
    id: Mapped[UUID] = _uuid_pk()
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    github_id: Mapped[int] = mapped_column(BigInteger)
    full_name: Mapped[str] = mapped_column(String(200))
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)


class BuildEvent(Base):
    """One row per workflow run / deployment, updated in place as GitHub reports progress."""
    __tablename__ = "build_events"
    __table_args__ = (UniqueConstraint("org_id", "repo_id", "kind", "run_id"),)
    id: Mapped[UUID] = _uuid_pk()
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    repo_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # build | deploy
    run_id: Mapped[int] = mapped_column(BigInteger)
    workflow_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    head_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    conclusion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    html_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    event_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_delivery_id: Mapped[str] = mapped_column(String(64))


class AlertChannel(Base):
    __tablename__ = "alert_channels"
    id: Mapped[UUID] = _uuid_pk()
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # slack | discord
    url_ciphertext: Mapped[str] = mapped_column(Text)
    url_last4: Mapped[str] = mapped_column(String(4))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    """Append-only (enforced by DB grants in the migration: INSERT/SELECT only)."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    org_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


__all__ = ["AlertChannel", "AuditLog", "BuildEvent", "Installation", "Membership", "Organization", "Repository", "User"]
