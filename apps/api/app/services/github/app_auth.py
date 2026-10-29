"""GitHub App authentication: short-lived JWT -> installation token with narrowed permissions."""
import time

import httpx
import jwt

from app.core.config import Settings


def make_app_jwt(settings: Settings, *, now: float | None = None) -> str:
    iat = int(now if now is not None else time.time())
    claims = {"iat": iat - 60, "exp": iat + 9 * 60, "iss": settings.github_client_id}
    return jwt.encode(claims, settings.github_app_private_key.get_secret_value(), algorithm="RS256")


async def installation_token(client: httpx.AsyncClient, settings: Settings, installation_id: int) -> str:
    """Ask for the minimum permissions per call, even though the App may hold more."""
    resp = await client.post(
        f"https://api.github.com/app/installations/{int(installation_id)}/access_tokens",
        headers={"Authorization": f"Bearer {make_app_jwt(settings)}", "Accept": "application/vnd.github+json"},
        json={"permissions": {"actions": "read", "metadata": "read"}},
    )
    resp.raise_for_status()
    return str(resp.json()["token"])
