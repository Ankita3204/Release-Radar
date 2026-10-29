"""Destination validation for outbound alert webhooks (CWE-918).

Primary control: exact host + path-prefix allow-list per provider, https only,
no credentials in the URL, default port only. Because the host set is fixed to
Slack/Discord, user input can never steer a request at internal addresses.

Defence in depth: resolve the host and refuse any non-global address, which
would catch DNS poisoning or an allow-list mistake. The sender also disables
redirects and sets hard timeouts.
"""
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

PROVIDERS: dict[str, tuple[frozenset[str], str]] = {
    "slack": (frozenset({"hooks.slack.com"}), "/services/"),
    "discord": (frozenset({"discord.com", "discordapp.com"}), "/api/webhooks/"),
}
MAX_URL_LEN = 300


class DestinationRejected(ValueError):
    pass


def validate_url_shape(kind: str, url: str) -> None:
    if kind not in PROVIDERS:
        raise DestinationRejected("unknown provider")
    if len(url) > MAX_URL_LEN or any(c in url for c in " \t\r\n\\"):
        raise DestinationRejected("malformed url")
    parts = urlsplit(url)
    hosts, prefix = PROVIDERS[kind]
    if parts.scheme != "https":
        raise DestinationRejected("https required")
    if parts.username or parts.password:
        raise DestinationRejected("credentials in url are not allowed")
    if parts.hostname not in hosts:
        raise DestinationRejected("host not allowed")
    if parts.port not in (None, 443):
        raise DestinationRejected("port not allowed")
    if not parts.path.startswith(prefix) or ".." in parts.path or len(parts.path) <= len(prefix):
        raise DestinationRejected("path not allowed")
    if parts.fragment:
        raise DestinationRejected("fragment not allowed")


async def _resolve(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return [i[4][0] for i in infos]


async def validate_destination(kind: str, url: str, *, resolver=None) -> None:
    resolver = resolver or _resolve  # looked up at call time so tests can substitute DNS
    validate_url_shape(kind, url)
    host = urlsplit(url).hostname or ""
    try:
        addresses = await resolver(host)
    except OSError as exc:
        raise DestinationRejected("host does not resolve") from exc
    if not addresses or not all(ipaddress.ip_address(a).is_global for a in addresses):
        raise DestinationRejected("destination resolves to a non-public address")
