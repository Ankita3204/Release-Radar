"""Secret redaction shared by logging and the AI layer.

Anything that might contain credentials passes through here before it is
logged, stored as an embedding, or placed in an LLM prompt.
"""
import re
from typing import Any

SENSITIVE_KEY_PARTS = (
    "authorization", "token", "secret", "cookie", "password", "passwd",
    "webhook_url", "private_key", "api_key", "apikey", "session", "csrf", "ciphertext",
)

_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]+"),
    re.compile(r"https://(?:discord|discordapp)\.com/api/webhooks/\d+/[A-Za-z0-9._-]+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b"),  # JWT-shaped
]
REDACTED = "[REDACTED]"


def redact_text(text: str) -> str:
    for pat in _PATTERNS:
        text = pat.sub(REDACTED, text)
    return text


def neutralize_log_injection(text: str) -> str:
    """Stop attacker-controlled values from forging extra log lines (CWE-117)."""
    return text.replace("\r", "\\r").replace("\n", "\\n")


def redact_value(value: Any, key: str | None = None) -> Any:
    if key is not None and any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
        return REDACTED
    if isinstance(value, str):
        return neutralize_log_injection(redact_text(value))
    if isinstance(value, dict):
        return {k: redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(v) for v in value]
    return value
