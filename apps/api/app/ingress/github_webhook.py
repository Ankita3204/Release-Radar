"""Public GitHub webhook endpoint.

Trust model: NO session, NO cookies. The only credential is the HMAC
signature, so this router is deliberately separate from api/v1.

Order of operations (each step rejects before the next costs anything):
  1. body-size cap (middleware)           4. HMAC verification over raw bytes
  2. per-IP bad-signature throttle        5. replay dedupe on X-GitHub-Delivery
  3. header presence/shape checks         6. strict parse -> enqueue -> 202
"""
import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.logging import get_logger
from app.core.rate_limit import allow, client_ip
from app.ingress.verify import verify_signature
from app.services.events import SUPPORTED_EVENTS, parse_event

router = APIRouter()
log = get_logger()

_DELIVERY_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
_EVENT_RE = re.compile(r"^[a-z_]{1,40}$")
DEDUPE_TTL = 7 * 24 * 3600
BAD_SIG_LIMIT, BAD_SIG_WINDOW = 20, 300


def _json(status: int, body: dict) -> JSONResponse:
    return JSONResponse(body, status_code=status)


@router.post("/webhooks/github", include_in_schema=False)
async def github_webhook(request: Request) -> JSONResponse:
    redis = request.app.state.redis
    ip = client_ip(request)

    throttle_key = f"badsig:{ip}"
    failures = await redis.get(throttle_key)
    if failures is not None and int(failures) >= BAD_SIG_LIMIT:
        return _json(429, {"error": "rate_limited"})

    delivery = request.headers.get("x-github-delivery", "")
    event = request.headers.get("x-github-event", "")
    if not _DELIVERY_RE.match(delivery) or not _EVENT_RE.match(event):
        return _json(400, {"error": "bad_headers"})

    body = await request.body()  # raw bytes: signature covers exactly these
    secret = request.app.state.settings.github_webhook_secret.get_secret_value().encode()
    if not verify_signature(secret, body, request.headers.get("x-hub-signature-256")):
        await allow(redis, throttle_key, BAD_SIG_LIMIT, BAD_SIG_WINDOW)
        log.warning("webhook_bad_signature", delivery=delivery, gh_event=event, ip=ip)
        return _json(401, {"error": "invalid_signature"})  # same body for every failure cause

    dedupe_key = f"delivery:{delivery}"
    if not await redis.set(dedupe_key, "1", nx=True, ex=DEDUPE_TTL):
        return _json(200, {"status": "duplicate"})

    if event == "ping":
        return _json(200, {"status": "pong"})
    if event not in SUPPORTED_EVENTS:
        return _json(202, {"status": "ignored"})

    try:
        build = parse_event(event, json.loads(body))
    except (ValidationError, ValueError, TypeError):
        log.warning("webhook_unparseable", delivery=delivery, gh_event=event)
        return _json(202, {"status": "ignored"})
    if build is None:
        return _json(202, {"status": "ignored"})

    try:
        request.app.state.enqueue(build.to_json(), delivery)
    except Exception:  # broker down: release the dedupe key so GitHub's redelivery is accepted
        await redis.delete(dedupe_key)
        log.error("webhook_enqueue_failed", delivery=delivery)
        return _json(503, {"error": "unavailable"})
    return _json(202, {"status": "accepted"})
