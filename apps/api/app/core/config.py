"""Typed, fail-fast configuration.

Security purpose:
  * Required secrets have NO defaults. A missing value stops the process at
    startup instead of silently falling back to something guessable.
  * Production-only invariants (HTTPS origins, TLS to Redis/Postgres, strong
    webhook secret) are enforced here, not left to deployment checklists.
  * Secrets are SecretStr so they cannot leak through repr()/logging.
"""
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDERS = {"changeme", "change-me", "secret", "password", "test", "example", "xxx"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["dev", "test", "prod"]

    database_url: SecretStr
    redis_url: SecretStr

    # Origin of the Next.js app. It is the only browser-facing origin: the
    # browser talks to the API exclusively through the Next.js BFF proxy.
    web_origin: str

    github_app_id: str
    github_client_id: str
    github_client_secret: SecretStr
    github_app_private_key: SecretStr
    github_webhook_secret: SecretStr

    # "kid1:<base64url 32 bytes>,kid2:<...>" and which kid encrypts new data.
    encryption_keys: SecretStr
    encryption_current_key_id: str

    session_idle_seconds: int = 30 * 60
    session_absolute_seconds: int = 12 * 60 * 60
    api_max_body_bytes: int = 256 * 1024
    webhook_max_body_bytes: int = 1024 * 1024
    docs_enabled: bool = False

    @field_validator("github_webhook_secret")
    @classmethod
    def _strong_webhook_secret(cls, v: SecretStr) -> SecretStr:
        raw = v.get_secret_value()
        if len(raw) < 32 or raw.lower() in _PLACEHOLDERS:
            raise ValueError("GITHUB_WEBHOOK_SECRET must be a random value of at least 32 characters")
        return v

    @field_validator("web_origin")
    @classmethod
    def _origin_shape(cls, v: str) -> str:
        if v.endswith("/") or v.count("/") != 2 or not v.startswith(("http://", "https://")):
            raise ValueError("WEB_ORIGIN must be a bare origin such as https://app.example.com")
        return v

    @model_validator(mode="after")
    def _production_invariants(self) -> "Settings":
        if self.env != "prod":
            return self
        problems: list[str] = []
        if not self.web_origin.startswith("https://"):
            problems.append("WEB_ORIGIN must be https in prod")
        if not self.redis_url.get_secret_value().startswith("rediss://"):
            problems.append("REDIS_URL must use rediss:// (TLS) in prod")
        db = self.database_url.get_secret_value()
        if "ssl=" not in db and "sslmode=" not in db:
            problems.append("DATABASE_URL must require TLS (ssl=require) in prod")
        if self.docs_enabled:
            problems.append("DOCS_ENABLED must be false in prod")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
