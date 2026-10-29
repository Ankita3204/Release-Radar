from datetime import UTC
from uuid import uuid4

from app.core.crypto import KeyRing
from app.db.session import tenant_session
from app.models.tables import AlertChannel, BuildEvent, Repository
from app.repositories.tenant import AlertChannelRepository, BuildRepository
from tests.conftest import WEB_ORIGIN, login_as, make_org


async def _seed_build(factory, org_id, name="o/r"):
    from datetime import datetime
    async with factory() as s, s.begin():
        repo = Repository(org_id=org_id, github_id=abs(hash(name)) % 10**6, full_name=name)
        s.add(repo)
        await s.flush()
        b = BuildEvent(org_id=org_id, repo_id=repo.id, kind="build", run_id=1, status="completed", conclusion="failure",
                       event_ts=datetime.now(UTC), last_delivery_id="d")
        s.add(b)
    return b.id


async def test_requires_authentication(client):
    for path in ("/v1/builds", "/v1/me", "/v1/alerts", "/v1/metrics/dora"):
        assert (await client.get(path)).status_code == 401


async def test_tenant_isolation_on_lists_and_repository(client, factory, redis, settings):
    org_a, user_a = await make_org(factory, login="a")
    org_b, _ = await make_org(factory, login="b")
    await _seed_build(factory, org_a, "a/repo")
    b_build = await _seed_build(factory, org_b, "b/secret-repo")
    await login_as(client, redis, settings, org_a, user_a)
    names = [b["repo"] for b in (await client.get("/v1/builds")).json()]
    assert names == ["a/repo"]
    async with factory() as s:  # IDOR at the repository layer: org A cannot fetch org B's row by id
        assert await BuildRepository(s, org_a).get(b_build) is None


async def test_cannot_delete_other_tenants_alert_channel(client, factory, redis, settings):
    org_a, user_a = await make_org(factory, login="a")
    org_b, user_b = await make_org(factory, login="b")
    cid = uuid4()
    async with tenant_session(factory, org_b) as s:
        await AlertChannelRepository(s, org_b).add(AlertChannel(id=cid, org_id=org_b, kind="slack", url_ciphertext="x",
                                                                url_last4="abcd", created_by=user_b))
    data = await login_as(client, redis, settings, org_a, user_a)
    r = await client.delete(f"/v1/alerts/{cid}", headers={"Origin": WEB_ORIGIN, "X-CSRF-Token": data.csrf})
    assert r.status_code == 404
    async with factory() as s:
        assert len(await AlertChannelRepository(s, org_b).list()) == 1


async def test_viewer_cannot_manage_alerts(client, factory, redis, settings):
    org, user = await make_org(factory, login="v", role="viewer")
    data = await login_as(client, redis, settings, org, user, role="viewer")
    assert (await client.get("/v1/alerts")).status_code == 403
    r = await client.post("/v1/alerts", json={"kind": "slack", "url": "https://hooks.slack.com/services/T/B/xxxxxxxx"},
                          headers={"Origin": WEB_ORIGIN, "X-CSRF-Token": data.csrf})
    assert r.status_code == 403


async def test_csrf_and_origin_enforced(client, factory, redis, settings, monkeypatch):
    async def fake_resolver(_h): return ["34.0.0.1"]
    monkeypatch.setattr("app.services.alerts.ssrf._resolve", fake_resolver)
    org, user = await make_org(factory, login="o")
    data = await login_as(client, redis, settings, org, user)
    body = {"kind": "slack", "url": "https://hooks.slack.com/services/T000/B000/abcdefghijkl"}
    assert (await client.post("/v1/alerts", json=body)).status_code == 403                                   # no origin/token
    assert (await client.post("/v1/alerts", json=body, headers={"Origin": "https://evil.test", "X-CSRF-Token": data.csrf})).status_code == 403
    assert (await client.post("/v1/alerts", json=body, headers={"Origin": WEB_ORIGIN, "X-CSRF-Token": "wrong"})).status_code == 403
    ok = await client.post("/v1/alerts", json=body, headers={"Origin": WEB_ORIGIN, "X-CSRF-Token": data.csrf})
    assert ok.status_code == 201
    assert ok.json()["url_last4"] == "ijkl" and "hooks.slack" not in ok.text
    async with factory() as s:  # stored encrypted, bound to the row
        ch = (await AlertChannelRepository(s, org).list())[0]
        assert "hooks.slack.com" not in ch.url_ciphertext
        ring: KeyRing = client.app.state.keyring
        assert ring.decrypt(ch.url_ciphertext, aad=f"alertchannel:{org}:{ch.id}") == body["url"]


async def test_mass_assignment_and_validation_errors_do_not_echo_input(client, factory, redis, settings):
    org, user = await make_org(factory, login="o")
    data = await login_as(client, redis, settings, org, user)
    r = await client.post("/v1/alerts", json={"kind": "slack", "url": "x" * 30, "org_id": str(uuid4()), "secret": "TOPSECRET"},
                          headers={"Origin": WEB_ORIGIN, "X-CSRF-Token": data.csrf})
    assert r.status_code == 422 and "TOPSECRET" not in r.text


async def test_security_headers_and_no_docs(client):
    r = await client.get("/healthz")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"
    assert r.headers["x-request-id"]
    for p in ("/docs", "/openapi.json", "/redoc"):
        assert (await client.get(p)).status_code == 404
