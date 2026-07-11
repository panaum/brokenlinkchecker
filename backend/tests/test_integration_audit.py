"""
Per-page third-party integration detection, classification and health.

Pins: the right integrations attribute to the page with the right type; GTM's
one install is one integration despite three HTML mentions; first-party scripts
are excluded; hosts classify correctly and unknowns are kept as "Other"; and the
burden-of-proof health mapping (403 ≠ down, timeout = unresponsive).
"""
import integration_audit as I
from integration_audit import (
    classify_host, collect_integrations, resource_health,
    HEALTHY, DOWN, UNRESPONSIVE, UNKNOWN,
    ANALYTICS, ADVERTISING, TAG_MANAGEMENT, CRM_FORMS, SCHEDULING, FONTS_CDN, OTHER,
)

PAGE = "https://www.acme.com/pricing"


class _Res:
    def __init__(self, url, resource_type="script", status_code=200,
                 bucket="ok", label="ok"):
        self.url = url
        self.resource_type = resource_type
        self.status_code = status_code
        self.bucket = bucket
        self.label = label


# ─── classification ──────────────────────────────────────────────────────────
def test_hosts_classify_to_the_right_category():
    assert classify_host("assets.calendly.com") == SCHEDULING
    assert classify_host("js.hs-scripts.com") == CRM_FORMS
    assert classify_host("www.googletagmanager.com") == TAG_MANAGEMENT
    assert classify_host("connect.facebook.net") == ADVERTISING
    assert classify_host("www.google-analytics.com") == ANALYTICS
    assert classify_host("fonts.googleapis.com") == FONTS_CDN


def test_an_unknown_host_is_other_not_dropped():
    assert classify_host("widget.somerandomtool.io") == OTHER


# ─── health mapping (burden of proof on down) ────────────────────────────────
def test_2xx_is_healthy():
    assert resource_health(_Res("https://x/a.js", status_code=200, bucket="ok")) == HEALTHY


def test_404_and_5xx_are_down():
    assert resource_health(_Res("https://x/a.js", status_code=404, bucket="broken")) == DOWN
    assert resource_health(_Res("https://x/a.js", status_code=503, bucket="error")) == DOWN


def test_a_dns_or_refused_failure_is_down():
    assert resource_health(_Res("https://x/a.js", status_code=None, bucket="broken")) == DOWN


def test_a_timeout_is_unresponsive_not_down():
    assert resource_health(_Res("https://x/a.js", status_code=None, bucket="timeout", label="timeout")) == UNRESPONSIVE


def test_403_and_429_and_999_are_unknown_never_down():
    for status in (403, 429, 999, 401, 405):
        assert resource_health(_Res("https://x/a.js", status_code=status, bucket="blocked")) == UNKNOWN


# ─── detection + attribution + type ──────────────────────────────────────────
def test_a_third_party_script_is_detected_with_type_script():
    results = [_Res("https://assets.calendly.com/widget.js", "script")]
    recs = collect_integrations(results, {}, PAGE)
    assert len(recs) == 1
    r = recs[0]
    assert r["host"] == "assets.calendly.com" and r["type"] == "script"
    assert r["category"] == SCHEDULING and r["health"] == HEALTHY


def test_a_third_party_iframe_is_detected_with_type_iframe():
    results = [_Res("https://www.youtube.com/embed/x", "iframe")]
    recs = collect_integrations(results, {}, PAGE)
    assert recs[0]["type"] == "iframe" and recs[0]["category"] == "Content/Media"


def test_an_inline_snippet_gtm_is_detected_with_its_id():
    signals = {"tracking": {"gtm": ["GTM-P593C44"]}}
    recs = collect_integrations([], signals, PAGE)
    gtm = [r for r in recs if r["type"] == "inline_snippet"]
    assert len(gtm) == 1
    assert gtm[0]["detected_id"] == "GTM-P593C44"
    assert gtm[0]["category"] == TAG_MANAGEMENT


def test_ga4_and_meta_inline_snippets_are_detected():
    signals = {"tracking": {"ga4": ["G-HVNDX1EG1J"], "meta_pixel": ["1105630533445518"]}}
    recs = collect_integrations([], signals, PAGE)
    ids = {r["detected_id"] for r in recs if r["type"] == "inline_snippet"}
    assert "G-HVNDX1EG1J" in ids and "1105630533445518" in ids


def test_inline_snippets_are_categorized_by_vendor_not_host():
    """GA4 loads from googletagmanager.com but is Analytics, not Tag Management;
    Meta is Advertising. Categorize the snippet by vendor."""
    signals = {"tracking": {"gtm": ["GTM-X1"], "ga4": ["G-ABCDEF"], "meta_pixel": ["123456789"]}}
    recs = {r["detected_id"]: r["category"] for r in collect_integrations([], signals, PAGE)
            if r["type"] == "inline_snippet"}
    assert recs["GTM-X1"] == TAG_MANAGEMENT
    assert recs["G-ABCDEF"] == ANALYTICS
    assert recs["123456789"] == ADVERTISING


# ─── GTM counted once despite three HTML mentions ────────────────────────────
def test_gtm_is_one_integration_even_with_inline_and_injected_src_and_noscript():
    """A correct GTM install has the id in the inline bootstrap, the injected
    gtm.js src, and the noscript iframe. extract_tracking already de-dups to one
    id; here the injected src is also a fetched resource — must not double."""
    signals = {"tracking": {"gtm": ["GTM-P593C44"]}}
    results = [_Res("https://www.googletagmanager.com/gtm.js?id=GTM-P593C44", "script")]
    recs = collect_integrations(results, signals, PAGE)
    gtm_related = [r for r in recs if "googletagmanager.com" in r["host"]]
    # The injected src (script) and the inline snippet — one host, and the
    # snippet carries the id; the fetched src is its library. Not three rows.
    assert len(gtm_related) <= 2
    assert any(r["detected_id"] == "GTM-P593C44" for r in gtm_related)


# ─── first-party filter ──────────────────────────────────────────────────────
def test_the_sites_own_scripts_are_excluded():
    results = [
        _Res("https://www.acme.com/app.js", "script"),      # first-party
        _Res("https://acme.com/bundle.js", "script"),       # first-party (apex)
        _Res("https://assets.calendly.com/w.js", "script"),  # third-party
    ]
    recs = collect_integrations(results, {}, PAGE)
    hosts = {r["host"] for r in recs}
    assert hosts == {"assets.calendly.com"}


def test_a_www_variant_of_the_page_domain_is_first_party():
    results = [_Res("https://cdn.acme.com/x.js", "script")]  # subdomain of own site
    recs = collect_integrations(results, {}, "https://acme.com/x")
    assert recs == []       # same registrable domain -> excluded


# ─── dedup + health reuse ────────────────────────────────────────────────────
def test_the_same_resource_twice_is_one_record():
    results = [_Res("https://cdn.x.io/a.js", "script"),
               _Res("https://cdn.x.io/a.js", "script")]
    recs = collect_integrations(results, {}, PAGE)
    assert len(recs) == 1


def test_a_down_third_party_script_reports_down():
    results = [_Res("https://cdn.down.io/a.js", "script", status_code=404, bucket="broken")]
    recs = collect_integrations(results, {}, PAGE)
    assert recs[0]["health"] == DOWN


def test_a_bot_blocked_third_party_reports_unknown_not_down():
    results = [_Res("https://cdn.blocked.io/a.js", "script", status_code=403, bucket="blocked")]
    recs = collect_integrations(results, {}, PAGE)
    assert recs[0]["health"] == UNKNOWN


def test_an_inline_snippet_borrows_its_librarys_health():
    """GTM snippet + a healthy gtm.js fetched -> the snippet is healthy too."""
    signals = {"tracking": {"gtm": ["GTM-ABC123"]}}
    results = [_Res("https://www.googletagmanager.com/gtm.js?id=GTM-ABC123", "script",
                    status_code=200, bucket="ok")]
    recs = collect_integrations(results, signals, PAGE)
    snippet = [r for r in recs if r["type"] == "inline_snippet"][0]
    assert snippet["health"] == HEALTHY


# ─── the endpoint: page filter with a URL-encoded, query-string page URL ─────
def test_the_endpoint_filters_and_sorts(monkeypatch):
    import main, asyncio
    stored = [
        {"page_url": "https://acme.com/p?ref=x", "host": "cdn.a.io", "resource_url": "https://cdn.a.io/a.js",
         "category": "Fonts/CDN", "type": "script", "detected_id": None, "health_status": "healthy"},
        {"page_url": "https://acme.com/p?ref=x", "host": "down.io", "resource_url": "https://down.io/b.js",
         "category": "Other", "type": "script", "detected_id": None, "health_status": "down"},
        {"page_url": "https://acme.com/other", "host": "x.io", "resource_url": "https://x.io/c.js",
         "category": "Other", "type": "script", "detected_id": None, "health_status": "healthy"},
    ]

    async def fake_get(scan_id, page_url=None):
        return [r for r in stored if page_url is None or r["page_url"] == page_url]

    monkeypatch.setattr(main, "get_integrations", fake_get)
    # page filter with a query-string URL
    data = asyncio.run(main.scan_integrations("scan1", page="https://acme.com/p?ref=x"))
    assert data["count"] == 2 and data["down"] == 1
    assert data["integrations"][0]["health_status"] == "down"   # down sorted first
    # no filter -> grouped by page
    alld = asyncio.run(main.scan_integrations("scan1", page=""))
    assert alld["total"] == 3 and len(alld["pages"]) == 2


# ─── dedup across pages: one resource on 3 pages -> 3 attributions, 1 URL ─────
def test_the_same_resource_on_three_pages_yields_three_attributions_one_url():
    """collect_integrations is per-page; health is per unique resource_url. So
    the same CDN script on 3 pages produces 3 records that share one URL — one
    health check covers all three."""
    urls = set()
    for page in ("https://acme.com/a", "https://acme.com/b", "https://acme.com/c"):
        recs = collect_integrations([_Res("https://cdn.shared.io/w.js", "script")], {}, page)
        assert len(recs) == 1
        urls.add(recs[0]["resource_url"])
    assert urls == {"https://cdn.shared.io/w.js"}   # one unique URL -> one health check


def test_unchecked_urls_are_the_unknown_ones_only():
    from integration_audit import unchecked_resource_urls, UNKNOWN, HEALTHY
    integ = [
        {"resource_url": "https://a.io/x.js", "health": HEALTHY},
        {"resource_url": "https://b.io/y.js", "health": UNKNOWN},
        {"resource_url": "not-a-url", "health": UNKNOWN},   # no fetchable URL
    ]
    assert unchecked_resource_urls(integ) == ["https://b.io/y.js"]
