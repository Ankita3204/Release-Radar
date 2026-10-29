"""Slack / Discord failure notifications.

Build metadata (branch, workflow name) is attacker-influenced, so:
  * Slack: &, <, > are escaped so `<!channel>` / link injection cannot fire.
  * Discord: allowed_mentions.parse = [] disables every @mention/ping.
  * Inline values are rendered in code spans with backticks removed.
"""
import httpx

from app.core.logging import get_logger
from app.services.alerts.ssrf import DestinationRejected, validate_destination

log = get_logger()


def _slack_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _code(s: str | None, limit: int = 80) -> str:
    return "`" + (s or "unknown").replace("`", "'").replace("\n", " ")[:limit] + "`"


def failure_payload(kind: str, *, repo: str, workflow: str | None, branch: str | None, conclusion: str | None,
                    url: str | None, what: str) -> dict:
    line = f"{what} {conclusion or 'failed'} in {_code(repo, 200)} — {_code(workflow)} on {_code(branch)}"
    if kind == "slack":
        text = _slack_escape(line)
        if url:
            text += f"\n<{url}|Open on GitHub>"
        return {"text": text, "link_names": 0, "unfurl_links": False}
    if kind == "discord":
        content = line + (f"\n<{url}>" if url else "")
        return {"content": content[:1900], "allowed_mentions": {"parse": []}}
    raise ValueError("unknown provider")


async def send(kind: str, url: str, payload: dict, *, client: httpx.AsyncClient | None = None) -> bool:
    """Returns True on 2xx. The URL is a bearer secret and is never logged."""
    try:
        await validate_destination(kind, url)  # re-validate at send time, not just at save time
    except DestinationRejected:
        log.warning("alert_destination_rejected", kind=kind)
        return False
    owns = client is None
    client = client or httpx.AsyncClient(follow_redirects=False, timeout=httpx.Timeout(5.0, connect=3.0))
    try:
        resp = await client.post(url, json=payload)
        ok = 200 <= resp.status_code < 300
        log.info("alert_sent", kind=kind, status=resp.status_code, ok=ok)
        return ok
    except httpx.HTTPError as exc:
        log.warning("alert_send_failed", kind=kind, error_type=type(exc).__name__)
        return False
    finally:
        if owns:
            await client.aclose()
