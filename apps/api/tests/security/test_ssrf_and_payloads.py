import pytest

from app.services.alerts.senders import failure_payload
from app.services.alerts.ssrf import DestinationRejected, validate_destination


async def public(_h):
    return ["34.1.2.3"]


async def private(_h):
    return ["169.254.169.254"]


GOOD_SLACK = "https://hooks.slack.com/services/T000/B000/abcdefgh"


@pytest.mark.parametrize("kind,url", [
    ("slack", "http://hooks.slack.com/services/T/B/x"),                    # not https
    ("slack", "https://hooks.slack.com.evil.test/services/T/B/x"),         # suffix trick
    ("slack", "https://evil.test/hooks.slack.com/services/T/B/x"),
    ("slack", "https://user:pw@hooks.slack.com/services/T/B/xxxx"),        # credentials
    ("slack", "https://hooks.slack.com:8443/services/T/B/xxxx"),           # odd port
    ("slack", "https://169.254.169.254/services/x"),                       # metadata service
    ("slack", "https://hooks.slack.com/services/../admin"),                # traversal
    ("slack", "https://hooks.slack.com/other/T/B/xxxx"),
    ("discord", "https://hooks.slack.com/services/T/B/xxxx"),              # wrong provider
    ("slack", "https://hooks.slack.com/services/T/B/xxxx\r\nHost: evil"),  # header injection
])
async def test_rejected_destinations(kind, url):
    with pytest.raises(DestinationRejected):
        await validate_destination(kind, url, resolver=public)


async def test_accepts_real_shapes_and_blocks_private_resolution():
    await validate_destination("slack", GOOD_SLACK, resolver=public)
    await validate_destination("discord", "https://discord.com/api/webhooks/123456789/abcDEF-ghi_jkl", resolver=public)
    with pytest.raises(DestinationRejected):
        await validate_destination("slack", GOOD_SLACK, resolver=private)  # DNS-rebinding style answer


def test_alert_text_cannot_ping_or_inject_links():
    p = failure_payload("slack", repo="o/r", workflow="<!channel> ci", branch="`x`<http://evil|click>", conclusion="failure",
                        url="https://github.com/o/r/actions/runs/1", what="Build")
    assert "<!channel>" not in p["text"] and "<http://evil" not in p["text"] and p["link_names"] == 0
    d = failure_payload("discord", repo="o/r", workflow="@everyone", branch="main", conclusion="failure", url=None, what="Build")
    assert d["allowed_mentions"] == {"parse": []}
