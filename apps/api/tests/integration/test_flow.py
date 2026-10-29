import json
from urllib.parse import parse_qs, urlparse

import httpx
import jwt as pyjwt
from sqlalchemy import select

from app.core.security import OAUTH_COOKIE, SESSION_COOKIE
from app.models.tables import BuildEvent, Installation
from app.services.events import ingest, parse_event
from app.services.github.app_auth import make_app_jwt
from tests.conftest import WEB_ORIGIN, make_org
from tests.security.test_webhook import payload


async def test_oauth_happy_path_and_login_csrf(client, github_handler, factory):
    r = await client.get("/v1/auth/github/login")
    assert r.status_code == 302
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["code_challenge_method"] == ["S256"] and q["redirect_uri"] == [f"{WEB_ORIGIN}/api/v1/auth/github/callback"]
    state = q["state"][0]
    set_cookie = r.headers["set-cookie"]
    assert OAUTH_COOKIE in set_cookie and "HttpOnly" in set_cookie and "Secure" in set_cookie and "SameSite=lax" in set_cookie

    # callback with a state the browser never held -> rejected
    bad = await client.get("/v1/auth/github/callback", params={"code": "c", "state": "forged"})
    assert bad.headers["location"].endswith("/login?error=oauth") and SESSION_COOKIE not in bad.headers.get("set-cookie", "")

    def gh(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if u.endswith("/login/oauth/access_token"):
            assert b"code_verifier" in request.content
            return httpx.Response(200, json={"access_token": "ghu_" + "a" * 30})
        if u.endswith("/user"):
            return httpx.Response(200, json={"id": 42, "login": "ashu", "avatar_url": "https://avatars.githubusercontent.com/u/42"})
        if u.endswith("/user/installations"):
            return httpx.Response(200, json={"installations": [
                {"id": 777, "account": {"type": "User", "id": 42, "login": "ashu"}},
                {"id": 888, "account": {"type": "Organization", "id": 5, "login": "bigcorp"}}]})
        if "/user/memberships/orgs/" in u:
            return httpx.Response(200, json={"role": "member", "state": "active"})  # not an admin -> must not link
        return httpx.Response(404)
    github_handler["fn"] = gh

    client.cookies.set(OAUTH_COOKIE, state)
    ok = await client.get("/v1/auth/github/callback", params={"code": "abc", "state": state})
    assert ok.status_code == 302 and ok.headers["location"] == f"{WEB_ORIGIN}/dashboard"
    assert SESSION_COOKIE in ok.headers["set-cookie"]
    me = await client.get("/v1/me")
    assert me.status_code == 200 and me.json()["login"] == "ashu" and me.json()["role"] == "owner"
    async with factory() as s:
        linked = set(await s.scalars(select(Installation.installation_id)))
    assert linked == {777}  # org install not claimable by a non-admin member

    replay = await client.get("/v1/auth/github/callback", params={"code": "abc", "state": state})
    assert replay.headers["location"].endswith("/login?error=oauth")  # state is single-use


async def test_logout_requires_csrf_and_kills_session(client, factory, redis, settings):
    from tests.conftest import login_as
    org, user = await make_org(factory)
    data = await login_as(client, redis, settings, org, user)
    assert (await client.post("/v1/auth/logout")).status_code == 403
    assert (await client.post("/v1/auth/logout", headers={"Origin": WEB_ORIGIN, "X-CSRF-Token": data.csrf})).status_code == 204
    assert (await client.get("/v1/me")).status_code == 401


async def test_ingest_is_idempotent_ordered_and_alerts_once(factory):
    org, _ = await make_org(factory, installation_id=111)
    fail = parse_event("workflow_run", payload(conclusion="failure"))
    first = await ingest(factory, fail, "d1")
    again = await ingest(factory, fail, "d2")                                  # redelivery under a new id
    assert first.should_alert and not again.should_alert
    stale = payload(conclusion="success")
    stale["workflow_run"]["updated_at"] = "2026-09-01T00:00:00Z"               # older than what we have
    await ingest(factory, parse_event("workflow_run", stale), "d3")
    async with factory() as s:
        rows = list(await s.scalars(select(BuildEvent)))
        assert len(rows) == 1 and rows[0].conclusion == "failure"
    assert await ingest(factory, parse_event("workflow_run", payload(install=999)), "d4") is None  # unknown installation


async def test_worker_sends_alert_with_decrypted_destination(factory, settings, monkeypatch):
    from uuid import uuid4

    from app.core.crypto import KeyRing
    from app.db.session import tenant_session
    from app.models.tables import AlertChannel
    from app.repositories.tenant import AlertChannelRepository
    from app.workers.tasks.events import run_ingest_and_alert

    org, user = await make_org(factory, installation_id=111)
    ring = KeyRing(settings.encryption_keys.get_secret_value(), settings.encryption_current_key_id)
    url, cid = "https://hooks.slack.com/services/T000/B000/abcdefgh", uuid4()
    async with tenant_session(factory, org) as s:
        await AlertChannelRepository(s, org).add(AlertChannel(
            id=cid, org_id=org, kind="slack", url_last4="efgh", created_by=user,
            url_ciphertext=ring.encrypt(url, aad=f"alertchannel:{org}:{cid}")))

    async def public(_h): return ["34.1.2.3"]
    monkeypatch.setattr("app.services.alerts.ssrf._resolve", public)
    sent = []
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: (sent.append((str(r.url), json.loads(r.content))), httpx.Response(200))[1]))
    build = parse_event("workflow_run", payload()).to_json()
    await run_ingest_and_alert(factory, ring, build, "d1", http)
    await run_ingest_and_alert(factory, ring, build, "d2", http)               # duplicate -> no second alert
    assert len(sent) == 1 and sent[0][0] == url and "o/r" in sent[0][1]["text"]


def test_app_jwt_is_rs256_with_short_expiry(settings):
    token = make_app_jwt(settings, now=1_800_000_000)
    claims = pyjwt.decode(token, options={"verify_signature": False})
    assert pyjwt.get_unverified_header(token)["alg"] == "RS256" and claims["exp"] - claims["iat"] <= 600
