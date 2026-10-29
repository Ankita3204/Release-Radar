"""GitHub sign-in (GitHub App user-to-server OAuth).

Hardening:
  * `state` is random, stored server-side (hashed), AND mirrored in a short-lived
    __Host- cookie; both must match (login CSRF, CWE-352).
  * PKCE (S256) on top of the client secret.
  * Redirect URI is fixed from config; the post-login destination is a constant
    (no `next=` parameter -> no open redirect, CWE-601).
  * The user's GitHub token is used inside this request only and never stored.
  * Installations are linked to an org only if the user owns the account or is
    an org admin; an installation already linked elsewhere is never re-assigned.
"""
import base64
import hashlib
import hmac
import secrets
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import tenant_db
from app.core.logging import get_logger
from app.core.rate_limit import client_ip, rate_limit
from app.core.security import (
    OAUTH_COOKIE,
    SESSION_COOKIE,
    SessionData,
    create_session,
    current_session,
    destroy_session,
    require_csrf,
)
from app.db.session import tenant_session
from app.models.tables import Installation, Membership, Organization, User
from app.repositories.tenant import AuditRepository
from app.schemas.api import MeOut

router = APIRouter(prefix="/v1")
log = get_logger()
GITHUB_API = "https://api.github.com"


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _cookie(resp: Response, name: str, value: str, max_age: int) -> None:
    resp.set_cookie(name, value, max_age=max_age, httponly=True, secure=True, samesite="lax", path="/")


def _fail(web_origin: str, reason: str = "oauth") -> RedirectResponse:
    resp = RedirectResponse(f"{web_origin}/login?error={reason}", status_code=302)
    resp.delete_cookie(OAUTH_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return resp


@router.get("/auth/github/login", dependencies=[Depends(rate_limit("login", 20, 60))])
async def login(request: Request) -> RedirectResponse:
    st = request.app.state.settings
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    await request.app.state.redis.set(f"oauth:{_sha(state)}", verifier, ex=600)
    query = urlencode({
        "client_id": st.github_client_id, "redirect_uri": f"{st.web_origin}/api/v1/auth/github/callback",
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    })
    resp = RedirectResponse(f"https://github.com/login/oauth/authorize?{query}", status_code=302)
    _cookie(resp, OAUTH_COOKIE, state, 600)
    return resp


@router.get("/auth/github/callback", dependencies=[Depends(rate_limit("callback", 20, 60))])
async def callback(request: Request, code: str = Query("", max_length=200), state: str = Query("", max_length=200)):
    st = request.app.state.settings
    redis = request.app.state.redis
    cookie_state = request.cookies.get(OAUTH_COOKIE, "")
    if not code or not state or not hmac.compare_digest(cookie_state.encode(), state.encode()):
        return _fail(st.web_origin)
    verifier = await redis.getdel(f"oauth:{_sha(state)}")  # single use
    if verifier is None:
        return _fail(st.web_origin)

    http: httpx.AsyncClient = request.app.state.http
    try:
        tok = await http.post("https://github.com/login/oauth/access_token", headers={"Accept": "application/json"}, data={
            "client_id": st.github_client_id, "client_secret": st.github_client_secret.get_secret_value(),
            "code": code, "redirect_uri": f"{st.web_origin}/api/v1/auth/github/callback", "code_verifier": verifier,
        })
        access = tok.json().get("access_token")
        if tok.status_code != 200 or not isinstance(access, str):
            return _fail(st.web_origin)
        auth = {"Authorization": f"Bearer {access}", "Accept": "application/vnd.github+json"}
        me = (await http.get(f"{GITHUB_API}/user", headers=auth)).json()
        inst_resp = await http.get(f"{GITHUB_API}/user/installations", headers=auth)
        installs = inst_resp.json().get("installations", []) if inst_resp.status_code == 200 else []
        admin_orgs: set[str] = set()
        for inst in installs:
            acct = inst.get("account", {})
            if acct.get("type") == "Organization":
                m = await http.get(f"{GITHUB_API}/user/memberships/orgs/{acct.get('login')}", headers=auth)
                if m.status_code == 200 and m.json().get("role") == "admin" and m.json().get("state") == "active":
                    admin_orgs.add(acct["login"])  # fail closed on any other answer
        del access, auth
        github_id, login_name = int(me["id"]), str(me["login"])[:100]
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        log.warning("oauth_exchange_failed")
        return _fail(st.web_origin)

    avatar = me.get("avatar_url")
    avatar = avatar if isinstance(avatar, str) and avatar.startswith("https://avatars.githubusercontent.com/") else None

    factory = request.app.state.session_factory
    async with factory() as db, db.begin():
        user = await db.scalar(select(User).where(User.github_id == github_id))
        if user is None:
            user = User(github_id=github_id, login=login_name, avatar_url=avatar)
            db.add(user)
            await db.flush()
        else:
            user.login, user.avatar_url = login_name, avatar
        membership = await db.scalar(select(Membership).where(Membership.user_id == user.id).order_by(Membership.id))
        if membership is None:
            org = Organization(id=uuid4(), name=f"{login_name}'s workspace")
            db.add(org)
            await db.flush()
            membership = Membership(org_id=org.id, user_id=user.id, role="owner")
            db.add(membership)
            await db.flush()
        org_id, role, user_id = membership.org_id, membership.role, user.id

    async with tenant_session(factory, org_id) as db:
        for inst in installs:
            acct = inst.get("account", {})
            owns = acct.get("type") == "User" and acct.get("id") == github_id
            if not (owns or acct.get("login") in admin_orgs) or role not in ("owner", "admin"):
                continue
            existing = await db.scalar(select(Installation).where(Installation.installation_id == inst["id"]))
            if existing is None:
                db.add(Installation(installation_id=int(inst["id"]), org_id=org_id, account_login=str(acct["login"])[:100]))
        await AuditRepository(db, org_id).append(actor=user_id, action="auth.login", ip=client_ip(request))

    sid, _ = await create_session(redis, st, user_id=user_id, org_id=org_id, role=role)  # fresh id: no fixation
    resp = RedirectResponse(f"{st.web_origin}/dashboard", status_code=302)
    resp.delete_cookie(OAUTH_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    _cookie(resp, SESSION_COOKIE, sid, st.session_absolute_seconds)
    return resp


@router.get("/me", response_model=MeOut)
async def me(session: SessionData = Depends(current_session), db: AsyncSession = Depends(tenant_db)) -> MeOut:
    user = await db.get(User, session.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return MeOut(login=user.login, avatar_url=user.avatar_url, role=session.role, csrf_token=session.csrf)


@router.post("/auth/logout", status_code=204, dependencies=[Depends(require_csrf)])
async def logout(request: Request) -> Response:
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        await destroy_session(request.app.state.redis, sid)
    resp = Response(status_code=204)
    resp.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return resp
