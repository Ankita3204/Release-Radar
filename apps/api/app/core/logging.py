"""Structured JSON logging with mandatory redaction."""
import logging
from typing import Any

import structlog

from app.core.redaction import redact_value


def redact_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return {k: redact_value(v, k) for k, v in event_dict.items()}


def configure_logging(env: str) -> None:
    renderer = structlog.dev.ConsoleRenderer() if env == "dev" else structlog.processors.JSONRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_processor,  # always last before rendering
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str = "releaseradar") -> Any:
    return structlog.get_logger(name)
