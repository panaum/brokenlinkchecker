"""
Bot-block detection + status classification tests.
"""
import asyncio

import httpx
import pytest

from checker import _is_bot_blocked, bucket_for_label, check_single, classify
from models import RawLink


def _resp(status=200, body="", headers=None):
    return httpx.Response(
        status_code=status,
        headers=headers or {},
        content=body.encode("utf-8"),
    )


# ─── Healthy 200 pages that must NOT be treated as bot-blocked ────────────────
def test_meta_robots_not_blocked():
    body = '<html><head><meta name="robots" content="index,follow"></head><body>Hi</body></html>'
    assert _is_bot_blocked(_resp(200, body)) is False


def test_automated_marketing_copy_not_blocked():
    body = "<html><body>Our automated workflows save you hours every week.</body></html>"
    assert _is_bot_blocked(_resp(200, body)) is False


def test_recaptcha_script_not_blocked():
    body = '<html><body><script src="https://www.google.com/recaptcha/api.js"></script>Contact us</body></html>'
    assert _is_bot_blocked(_resp(200, body)) is False


def test_blocked_word_in_copy_not_blocked():
    body = "<html><body>Nothing here is blocked or restricted. Enjoy!</body></html>"
    assert _is_bot_blocked(_resp(200, body)) is False


# ─── Genuine challenge / block responses that MUST be blocked ─────────────────
def test_cloudflare_just_a_moment_403_blocked():
    body = "<html><head><title>Just a moment...</title></head><body>Checking your browser</body></html>"
    assert _is_bot_blocked(_resp(403, body)) is True


def test_cloudflare_server_503_blocked():
    assert _is_bot_blocked(_resp(503, "server error", headers={"server": "cloudflare"})) is True


def test_cf_mitigated_header_blocked():
    assert _is_bot_blocked(_resp(403, "", headers={"cf-mitigated": "challenge"})) is True


def test_px_captcha_403_blocked():
    body = "<html><body>px-captcha challenge required</body></html>"
    assert _is_bot_blocked(_resp(403, body)) is True


# ─── classify() ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("status,expected", [
    (200, "ok"),
    (204, "ok"),
    (301, "redirect"),
    (302, "redirect"),
    (401, "blocked"),
    (403, "blocked"),
    (405, "blocked"),
    (429, "blocked"),
    (999, "blocked"),
    (404, "broken"),
    (410, "broken"),
    (500, "error"),
    (503, "error"),
    (None, "timeout"),
])
def test_classify(status, expected):
    assert classify(status) == expected


# ─── Part D bucket mapping ───────────────────────────────────────────────────
# Provable failures are "broken"; anything we cannot judge is "unverifiable".
@pytest.mark.parametrize("status,expected_bucket", [
    # provable failures
    (404, "broken"),
    (410, "broken"),
    (500, "broken"),
    (502, "broken"),
    (503, "broken"),
    # cannot judge from here — never a red bucket
    (401, "unverifiable"),
    (403, "unverifiable"),
    (405, "unverifiable"),
    (429, "unverifiable"),
    (999, "unverifiable"),
    (None, "unverifiable"),   # timeout
    # healthy links belong to no issue bucket
    (200, "ok"),
    (301, "ok"),
])
def test_status_maps_to_bucket(status, expected_bucket):
    assert bucket_for_label(classify(status)) == expected_bucket


def test_dns_and_connection_errors_are_broken():
    """Transport-level failures surface as label 'error' -> provable breakage."""
    assert bucket_for_label("error") == "broken"


def test_bot_blocked_is_unverifiable():
    assert bucket_for_label("blocked") == "unverifiable"


def test_unknown_label_defaults_to_unverifiable():
    """When the tool is not sure, the item must not land in a red bucket."""
    assert bucket_for_label("something-new") == "unverifiable"


# ─── check_single end-to-end: the LinkResult must carry the right bucket ─────
def _raw(**over) -> RawLink:
    fields = dict(
        url="https://acme.test/page",
        source_element="a",
        anchor_text="Link",
        category="Body text",
        is_external=False,
    )
    fields.update(over)
    return RawLink(**fields)


def _check(link: RawLink, status: int = 200) -> "object":
    async def run():
        transport = httpx.MockTransport(lambda req: httpx.Response(status))
        async with httpx.AsyncClient(transport=transport) as client:
            return await check_single(client, link)
    return asyncio.run(run())


def test_check_single_sets_broken_bucket_on_404():
    r = _check(_raw(), status=404)
    assert r.label == "broken"
    assert r.bucket == "broken"


def test_check_single_sets_unverifiable_bucket_on_429():
    r = _check(_raw(), status=429)
    assert r.label == "blocked"
    assert r.bucket == "unverifiable"


def test_check_single_healthy_link_is_not_in_an_issue_bucket():
    r = _check(_raw(), status=200)
    assert r.label == "ok"
    assert r.bucket == "ok"


def test_check_single_preserves_detector_bucket_for_dead_ctas():
    """A low-confidence dead CTA stays 'unverifiable' — the checker must not
    overwrite the detector's own judgement from the 'dead_cta' label."""
    link = _raw(category="Dead CTA", confidence="low", bucket="unverifiable",
                reason="Button has no static handler")
    r = _check(link)
    assert r.label == "dead_cta"
    assert r.bucket == "unverifiable"
    assert r.reason == "Button has no static handler"


def test_check_single_keeps_high_confidence_dead_cta_bucket():
    link = _raw(category="Dead CTA", confidence="high", bucket="dead_cta")
    r = _check(link)
    assert r.bucket == "dead_cta"
