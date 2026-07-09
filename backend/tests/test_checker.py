"""
Bot-block detection + status classification tests.
"""
import asyncio

import httpx
import pytest

from checker import (
    _fragment_present,
    _is_bot_blocked,
    bucket_for_label,
    check_single,
    classify,
    classify_exception,
    validate_contact,
)
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


# ─── mailto: / tel: validation (never fetched) ───────────────────────────────
@pytest.mark.parametrize("url,ok", [
    ("mailto:info@gounitedrealty.com", True),
    ("mailto:a.b+tag@sub.example.co.uk", True),
    ("mailto:one@x.com,two@y.com", True),
    ("mailto:hi@site.test?subject=Hello%20there", True),
    ("mailto:not-an-email", False),
    ("mailto:missing@tld", False),
    ("mailto:", False),
    ("tel:+15551234567", True),
    ("tel:7084482900", True),
    ("tel:(708) 448-2900", True),
    ("tel:123", False),
    ("tel:call-us-now", False),
    ("tel:", False),
])
def test_validate_contact(url, ok):
    assert validate_contact(url)[0] is ok


def test_contact_link_is_not_fetched_and_reports_ok():
    r = _check(_raw(url="mailto:info@site.test", link_kind="contact"))
    assert r.label == "ok" and r.bucket == "ok" and r.status_code is None


def test_malformed_contact_link_is_broken_with_a_reason():
    r = _check(_raw(url="tel:123", link_kind="contact"))
    assert r.label == "broken" and r.bucket == "broken"
    assert "too short" in r.error.lower()


def test_resolved_in_page_anchor_reports_ok_without_fetching():
    r = _check(_raw(url="https://acme.test/#services", link_kind="anchor", fragment="services"))
    assert r.label == "ok" and r.bucket == "ok" and r.response_ms == 0


# ─── cross-page fragment validation ─────────────────────────────────────────
@pytest.mark.parametrize("body,frag,present", [
    ('<div id="team"></div>', "team", True),
    ("<div id='team'></div>", "team", True),
    ("<div id=team></div>", "team", True),
    ('<a name="team"></a>', "team", True),
    ('<div id="TEAM"></div>', "team", True),
    ('<div id="teams"></div>', "team", False),      # must not match a prefix
    ('<div id="our-team"></div>', "team", False),
    ("<p>team</p>", "team", False),                  # text is not an anchor target
])
def test_fragment_present(body, frag, present):
    assert _fragment_present(body, frag) is present


def _check_html(link, status=200, body="", headers=None):
    async def run():
        def handler(req):
            return httpx.Response(status, html=body) if body else httpx.Response(status)
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await check_single(client, link)
    return asyncio.run(run())


def test_missing_fragment_on_script_free_page_is_flagged():
    """/about-us/#team returns 200 whether or not #team exists — HTTP never sees
    the fragment. With no JS on the page, the absence is provable."""
    link = _raw(url="https://acme.test/about-us/#team", fragment="team")
    r = _check_html(link, body="<html><body><h1>About</h1></body></html>")
    assert r.label == "dead_cta"
    assert r.bucket == "dead_cta"
    assert "#team" in r.error and "/about-us/" in r.error


def test_present_fragment_on_target_page_is_ok():
    link = _raw(url="https://acme.test/about-us/#team", fragment="team")
    r = _check_html(link, body='<html><body><section id="team"></section></body></html>')
    assert r.label == "ok" and r.bucket == "ok"


def test_missing_fragment_on_js_rendered_page_is_unverifiable():
    """We fetch without JS, so a missing id on an SPA proves nothing."""
    link = _raw(url="https://acme.test/app/#team", fragment="team")
    r = _check_html(link, body='<html><body><div id="root" data-reactroot=""></div></body></html>')
    assert r.bucket == "unverifiable"
    assert "javascript" in r.error.lower()


def test_missing_fragment_on_a_page_with_scripts_is_unverifiable():
    """Regression (found by validate_live against webflow.com): #recent on
    /discover/popular is a JS-rendered tab, absent from the static HTML.
    Any page carrying a <script> may build the target at runtime."""
    link = _raw(url="https://acme.test/discover/popular#recent", fragment="recent")
    body = '<html><body><script src="/app.js"></script><div class="tabs"></div></body></html>'
    r = _check_html(link, body=body)
    assert r.bucket == "unverifiable"
    assert r.confidence == "low"
    assert "check manually" in r.error.lower()


@pytest.mark.parametrize("fragment", [
    "url=http%3A%2F%2Fwebflow.com",   # validator.schema.org — state in the fragment
    "!/dashboard",                     # hash-bang routing
    "/getting-started",                # hash routing
    "page=3",
    "a=1&b=2",
])
def test_non_identifier_fragments_are_never_validated(fragment):
    """Regression (validate_live vs webflow.com): a fragment carrying client-side
    state never names an element, so 'section not found' is meaningless."""
    from checker import is_identifier_fragment
    assert is_identifier_fragment(fragment) is False

    link = _raw(url=f"https://acme.test/tool#{fragment}", fragment=fragment)
    r = _check_html(link, body="<html><body>no ids here</body></html>")
    assert r.label == "ok" and r.bucket == "ok"


@pytest.mark.parametrize("fragment", ["team", "idx-search", "section_2", "a.b:c"])
def test_identifier_fragments_are_validated(fragment):
    from checker import is_identifier_fragment
    assert is_identifier_fragment(fragment) is True


def test_non_html_response_never_triggers_a_fragment_flag():
    """A 200 that isn't an HTML document (PDF, JSON, challenge page) has no ids
    either — flagging it would be a false alarm."""
    link = _raw(url="https://acme.test/report.pdf#summary", fragment="summary")
    r = _check_html(link, body="%PDF-1.7 binary junk")
    assert r.label == "ok" and r.bucket == "ok"


def test_link_without_fragment_skips_the_check():
    link = _raw(url="https://acme.test/about-us/")
    r = _check_html(link, body="<html><body>no ids here</body></html>")
    assert r.label == "ok" and r.bucket == "ok"


# ─── Transport failures ─────────────────────────────────────────────────────
# Regression (found by validate_live against elegantthemes.com): checking 446
# links on one host made the server reset connections, and every reset was
# reported as a broken link — 39 false alarms on pages that return HTTP 200.
@pytest.mark.parametrize("exc,expected_bucket", [
    # provisionally broken — still subject to a direct resolver confirmation
    (httpx.ConnectError("[Errno -2] Name or service not known"), "broken"),
    (httpx.ConnectError("[Errno 11001] getaddrinfo failed"), "broken"),
    # never provable from the exception alone: a WAF RSTs connections just like
    # a closed port, and a throttled crawl produces all of these
    (httpx.ConnectError("[Errno 111] Connection refused"), "unverifiable"),
    (httpx.ReadError("[Errno 104] Connection reset by peer"), "unverifiable"),
    (httpx.RemoteProtocolError("Server disconnected without response"), "unverifiable"),
    (httpx.ConnectError("[SSL] certificate verify failed"), "unverifiable"),
    (httpx.PoolTimeout("pool timeout"), "unverifiable"),
    (httpx.ConnectTimeout("timed out"), "unverifiable"),
    (httpx.ReadTimeout("timed out"), "unverifiable"),
])
def test_classify_exception(exc, expected_bucket):
    assert classify_exception(exc)[1] == expected_bucket


def test_timeouts_stay_labelled_timeout():
    assert classify_exception(httpx.ReadTimeout("x"))[0] == "timeout"


def _check_raising(exc, monkeypatch=None, resolves=False):
    if monkeypatch is not None:
        async def fake_resolves(host):
            return resolves
        monkeypatch.setattr("checker.hostname_resolves", fake_resolves)

    async def run():
        def handler(req):
            raise exc
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await check_single(client, _raw())
    return asyncio.run(run())


def test_connection_reset_is_unverifiable_not_broken():
    """A throttled crawl must not turn healthy pages into 'broken' rows."""
    r = _check_raising(httpx.ReadError("[Errno 104] Connection reset by peer"))
    assert r.bucket == "unverifiable"
    assert "rate-limiting" in r.error.lower()


def test_dns_failure_on_a_dead_domain_is_broken(monkeypatch):
    """The hostname still fails to resolve when asked directly — a dead domain."""
    r = _check_raising(
        httpx.ConnectError("[Errno -2] Name or service not known"),
        monkeypatch, resolves=False,
    )
    assert r.bucket == "broken"
    assert "does not resolve" in r.error.lower()


def test_dns_failure_on_a_live_domain_is_unverifiable(monkeypatch):
    """Regression (validate_live vs allbirds.com): checking ~90 links overloaded
    the OS resolver, so facebook.com and even the site's own homepage raised
    getaddrinfo failures and were reported broken. If the host resolves on a
    direct query, the failure was overload — not a dead domain."""
    r = _check_raising(
        httpx.ConnectError("[Errno 11001] getaddrinfo failed"),
        monkeypatch, resolves=True,
    )
    assert r.bucket == "unverifiable"
    assert "rate-limiting" in r.error.lower()


def test_five_hundred_keeps_the_provable_bucket():
    assert bucket_for_label("error") == "broken"
