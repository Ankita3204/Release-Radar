import base64
import os

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.crypto import DecryptionError, KeyRing
from app.core.logging import redact_processor
from app.core.redaction import redact_text
from app.ingress.verify import compute_signature, verify_signature


def _key():
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def test_crypto_roundtrip_and_aad_binding():
    ring = KeyRing(f"k1:{_key()}", "k1")
    token = ring.encrypt("https://hooks.slack.com/services/T/B/x", aad="row:1")
    assert "hooks.slack.com" not in token
    assert ring.decrypt(token, aad="row:1").endswith("/x")
    with pytest.raises(DecryptionError):
        ring.decrypt(token, aad="row:2")  # ciphertext moved to another row/tenant


def test_crypto_tamper_and_rotation():
    k1, k2 = _key(), _key()
    old = KeyRing(f"k1:{k1}", "k1").encrypt("v", aad="a")
    ring = KeyRing(f"k1:{k1},k2:{k2}", "k2")
    assert ring.decrypt(old, aad="a") == "v" and ring.needs_rotation(old)
    parts = old.split(".")
    parts[3] = parts[3][:-2] + ("AA" if parts[3][-2:] != "AA" else "BB")
    with pytest.raises(DecryptionError):
        ring.decrypt(".".join(parts), aad="a")
    with pytest.raises(ValueError):
        KeyRing("k1:short", "k1")


def test_signature_verification():
    secret, body = b"s" * 40, b'{"a":1}'
    good = compute_signature(secret, body)
    assert verify_signature(secret, body, good)
    assert not verify_signature(secret, body + b" ", good)
    assert not verify_signature(secret, body, None)
    assert not verify_signature(secret, body, "sha1=" + "0" * 40)
    assert not verify_signature(secret, body, "sha256=" + "0" * 64)
    assert not verify_signature(b"x" * 40, body, good)


def test_redaction_and_log_injection():
    text = "token ghp_" + "a" * 36 + " hook https://hooks.slack.com/services/T000/B000/abcDEF"
    out = redact_text(text)
    assert "ghp_" not in out and "hooks.slack.com/services" not in out
    event = redact_processor(None, "info", {"event": "x\nFAKE LOG LINE", "authorization": "Bearer abc", "n": 1})
    assert "\n" not in event["event"] and event["authorization"] == "[REDACTED]"


def _env(**over):
    base = dict(env="prod", database_url="postgresql+asyncpg://u:p@h/d?ssl=require", redis_url="rediss://h:6379",
                web_origin="https://app.example.com", github_app_id="1", github_client_id="c", github_client_secret="s",
                github_app_private_key="k", github_webhook_secret="x" * 40, encryption_keys="k1:" + _key(),
                encryption_current_key_id="k1")
    base.update(over)
    return Settings(_env_file=None, **base)


def test_config_fail_fast():
    _env()  # valid prod config
    with pytest.raises(ValidationError):
        _env(redis_url="redis://h:6379")  # plaintext Redis in prod
    with pytest.raises(ValidationError):
        _env(web_origin="http://app.example.com")
    with pytest.raises(ValidationError):
        _env(github_webhook_secret="short")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, env="prod")  # nothing provided: no silent defaults
