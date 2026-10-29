import json

from app.ingress.verify import compute_signature
from tests.conftest import WEBHOOK_SECRET

SHA = "a" * 40


def payload(install=111, conclusion="failure"):
    return {
        "action": "completed",
        "workflow_run": {"id": 9, "name": "CI", "head_branch": "main", "head_sha": SHA, "status": "completed",
                         "conclusion": conclusion, "html_url": "https://github.com/o/r/actions/runs/9",
                         "updated_at": "2026-10-01T10:00:00Z"},
        "repository": {"id": 5, "full_name": "o/r", "default_branch": "main"},
        "installation": {"id": install},
    }


def headers(body: bytes, delivery="1b2c3d4e-0000-4000-8000-000000000001", event="workflow_run", secret=WEBHOOK_SECRET):
    return {"X-GitHub-Delivery": delivery, "X-GitHub-Event": event, "Content-Type": "application/json",
            "X-Hub-Signature-256": compute_signature(secret.encode(), body)}


async def test_valid_signature_accepted_and_normalized(client, enqueued):
    body = json.dumps(payload()).encode()
    r = await client.post("/webhooks/github", content=body, headers=headers(body))
    assert r.status_code == 202
    (build, delivery), = enqueued
    assert build["repo_full_name"] == "o/r" and build["conclusion"] == "failure" and delivery.startswith("1b2c")
    assert "workflow_run" not in build  # raw payload never reaches the queue


async def test_forged_and_tampered_signatures_rejected(client, enqueued):
    body = json.dumps(payload()).encode()
    r = await client.post("/webhooks/github", content=body, headers=headers(body, secret="z" * 40))
    assert r.status_code == 401
    h = headers(body)
    r = await client.post("/webhooks/github", content=body.replace(b"failure", b"success"), headers=h)
    assert r.status_code == 401
    h.pop("X-Hub-Signature-256")
    assert (await client.post("/webhooks/github", content=body, headers=h)).status_code == 401
    assert enqueued == []


async def test_replay_is_deduplicated(client, enqueued):
    body = json.dumps(payload()).encode()
    assert (await client.post("/webhooks/github", content=body, headers=headers(body))).status_code == 202
    again = await client.post("/webhooks/github", content=body, headers=headers(body))
    assert again.status_code == 200 and again.json()["status"] == "duplicate" and len(enqueued) == 1


async def test_bad_signature_throttle(client):
    body = b"{}"
    for _ in range(20):
        await client.post("/webhooks/github", content=body, headers=headers(body, secret="z" * 40))
    assert (await client.post("/webhooks/github", content=body, headers=headers(body))).status_code == 429


async def test_oversized_body_rejected_before_parsing(client):
    big = b"x" * (1024 * 1024 + 1)
    assert (await client.post("/webhooks/github", content=big, headers=headers(big))).status_code == 413

    async def chunks():  # chunked: no Content-Length, limit enforced while streaming
        for _ in range(20):
            yield b"x" * 100_000
    r = await client.post("/webhooks/github", content=chunks(), headers=headers(b""))
    assert r.status_code == 413


async def test_unknown_event_and_hostile_fields_are_ignored(client, enqueued):
    body = b'{"zen":"hi"}'
    r = await client.post("/webhooks/github", content=body, headers=headers(body, event="ping", delivery="1b2c3d4e-0000-4000-8000-000000000002"))
    assert r.status_code == 200
    bad = payload()
    bad["workflow_run"]["head_sha"] = "not-a-sha"
    body = json.dumps(bad).encode()
    r = await client.post("/webhooks/github", content=body, headers=headers(body, delivery="1b2c3d4e-0000-4000-8000-000000000003"))
    assert r.status_code == 202 and r.json()["status"] == "ignored" and enqueued == []


async def test_non_github_urls_are_dropped(client, enqueued):
    p = payload()
    p["workflow_run"]["html_url"] = "javascript:alert(1)"
    body = json.dumps(p).encode()
    await client.post("/webhooks/github", content=body, headers=headers(body))
    assert enqueued[0][0]["html_url"] is None


async def test_enqueue_failure_releases_dedupe_key(client, redis):
    client.app.state.enqueue = lambda *_: (_ for _ in ()).throw(RuntimeError("broker down"))
    body = json.dumps(payload()).encode()
    assert (await client.post("/webhooks/github", content=body, headers=headers(body))).status_code == 503
    assert await redis.get("delivery:1b2c3d4e-0000-4000-8000-000000000001") is None  # redelivery will be accepted
