"""
Full resource checking.

A page that returns HTTP 200 can still be broken: a 404 on a <script src> kills
every interaction, a dead <link rel=stylesheet> makes the page unreadable, and
neither shows up if you only follow <a href>.

Pure functions over a parsed DOM. No Playwright, no network.
"""
import asyncio

import httpx
import pytest
from bs4 import BeautifulSoup

from checker import check_single
from resources import (
    CSS_URL,
    FAVICON,
    IFRAME,
    IMAGE,
    META_IMAGE,
    SCRIPT,
    STYLESHEET,
    collect_resources,
    describe_resource_failure,
    extract_css_urls,
    host_breakdown,
    link_type_breakdown,
    parse_srcset,
    resources_from_stylesheets,
    scheme_breakdown,
)


PAGE = "https://acme.test/"


FIXTURE = """
<!doctype html>
<html>
<head>
  <link rel="stylesheet" href="/css/site.css">
  <link rel="icon" href="/favicon.ico">
  <meta property="og:image" content="https://cdn.acme.test/social.png">
  <meta name="twitter:image" content="/twitter.png">
  <script src="/js/app.js"></script>
  <style>
    .hero { background: url('/img/hero.jpg'); }
    .logo { background-image: url("data:image/png;base64,AAA"); }
    @import "/css/extra.css";
  </style>
</head>
<body>
  <a href="/about">About</a>
  <img src="/img/broken.png" srcset="/img/a.png 1x, /img/b.png 2x">
  <iframe src="https://embed.acme.test/widget"></iframe>
  <video src="/media/clip.mp4" poster="/img/poster.jpg"></video>
  <picture><source srcset="/img/pic.webp 1x"></picture>
  <div style="background: url(/img/inline.png)"></div>
  <script>console.log("inline, no src")</script>
  <img src="data:image/gif;base64,R0lGOD">
</body>
</html>
"""


def _resources():
    soup = BeautifulSoup(FIXTURE, "lxml")
    return {r.url: r for r in collect_resources(soup, PAGE)}


# ─── extraction ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("url,expected_type", [
    ("https://acme.test/css/site.css", STYLESHEET),
    ("https://acme.test/favicon.ico", FAVICON),
    ("https://acme.test/js/app.js", SCRIPT),
    ("https://acme.test/img/broken.png", IMAGE),
    ("https://acme.test/img/a.png", IMAGE),
    ("https://acme.test/img/b.png", IMAGE),
    ("https://embed.acme.test/widget", IFRAME),
    ("https://acme.test/img/hero.jpg", CSS_URL),
    ("https://acme.test/css/extra.css", CSS_URL),
    ("https://acme.test/img/inline.png", CSS_URL),
    ("https://cdn.acme.test/social.png", META_IMAGE),
    ("https://acme.test/twitter.png", META_IMAGE),
    ("https://acme.test/img/poster.jpg", IMAGE),
    ("https://acme.test/img/pic.webp", IMAGE),
])
def test_resource_is_extracted_and_typed(url, expected_type):
    resources = _resources()
    assert url in resources, f"{url} not extracted"
    assert resources[url].resource_type == expected_type


def test_anchors_are_not_resources():
    """<a href> is the crawler's job; resources must not duplicate it."""
    assert "https://acme.test/about" not in _resources()


def test_data_uris_are_never_fetched():
    assert not any(u.startswith("data:") for u in _resources())


def test_inline_script_without_src_is_not_a_resource():
    assert not any(r.resource_type == SCRIPT and r.url.endswith(".js") is False
                   for r in _resources().values())


def test_resources_are_marked_external_by_host():
    resources = _resources()
    assert resources["https://embed.acme.test/widget"].is_external is True
    assert resources["https://acme.test/js/app.js"].is_external is False


# ─── priority ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("url", [
    "https://acme.test/js/app.js",       # script
    "https://acme.test/css/site.css",    # stylesheet
])
def test_script_and_stylesheet_are_high_priority(url):
    """They break the page, not just its looks."""
    assert _resources()[url].priority == "high"


def test_image_is_not_high_priority():
    assert _resources()["https://acme.test/img/broken.png"].priority == "low"


# ─── srcset / css helpers ────────────────────────────────────────────────────
def test_parse_srcset_drops_descriptors():
    assert parse_srcset("a.png 1x, b.png 2x, c.png 100w") == ["a.png", "b.png", "c.png"]


def test_parse_srcset_handles_empty():
    assert parse_srcset("") == []
    assert parse_srcset("  ,  ") == []


@pytest.mark.parametrize("css,expected", [
    ("a{background:url(/x.png)}", ["https://acme.test/x.png"]),
    ("a{background:url('/x.png')}", ["https://acme.test/x.png"]),
    ('a{background:url("/x.png")}', ["https://acme.test/x.png"]),
    ("a{background:url( /x.png )}", ["https://acme.test/x.png"]),
    ('@import "/y.css";', ["https://acme.test/y.css"]),
    ("a{background:url(data:image/png;base64,AAA)}", []),
    ("a{background:none}", []),
])
def test_extract_css_urls(css, expected):
    assert extract_css_urls(css, PAGE) == expected


def test_resources_from_linked_stylesheets_resolve_against_the_sheet():
    """url(../img/x.png) in /css/site.css resolves relative to the stylesheet."""
    sheets = [{"href": "https://cdn.acme.test/css/site.css",
               "text": "a{background:url(../img/x.png)}"}]
    urls = [r.url for r in resources_from_stylesheets(sheets, PAGE)]
    assert urls == ["https://cdn.acme.test/img/x.png"]


def test_cross_origin_stylesheet_with_no_text_is_skipped():
    assert resources_from_stylesheets([{"href": "https://x.test/a.css", "text": ""}], PAGE) == []


# ─── the same URL used two ways ──────────────────────────────────────────────
def test_higher_impact_resource_type_wins_for_a_shared_url():
    """If one URL is both an <img> and a <script>, report the failure that
    actually breaks the page."""
    html = '<img src="/a.js"><script src="/a.js"></script>'
    resources = {r.url: r for r in collect_resources(BeautifulSoup(html, "lxml"), PAGE)}
    assert resources["https://acme.test/a.js"].resource_type == SCRIPT
    assert resources["https://acme.test/a.js"].priority == "high"


# ─── reason text ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("rtype,fragment", [
    (SCRIPT, "breaks page behaviour"),
    (STYLESHEET, "breaks page rendering"),
    (IMAGE, "broken image"),
    (CSS_URL, "background or font"),
])
def test_describe_resource_failure(rtype, fragment):
    text = describe_resource_failure(rtype)
    assert text.startswith("Broken ")
    assert fragment in text


# ─── bucketing through the checker ───────────────────────────────────────────
def _check(link, status: int):
    async def run():
        transport = httpx.MockTransport(lambda req: httpx.Response(status))
        async with httpx.AsyncClient(transport=transport) as client:
            return await check_single(client, link)
    return asyncio.run(run())


@pytest.mark.parametrize("url,rtype", [
    ("https://acme.test/img/broken.png", IMAGE),
    ("https://acme.test/js/app.js", SCRIPT),
    ("https://acme.test/css/site.css", STYLESHEET),
    ("https://acme.test/img/hero.jpg", CSS_URL),
])
def test_broken_resource_is_bucketed_broken_with_a_typed_reason(url, rtype):
    result = _check(_resources()[url], status=404)
    assert result.bucket == "broken"
    assert result.resource_type == rtype
    assert result.reason == describe_resource_failure(rtype)


def test_broken_script_keeps_high_priority():
    result = _check(_resources()["https://acme.test/js/app.js"], status=404)
    assert result.priority == "high"


def test_healthy_resource_has_no_priority_and_no_reason():
    result = _check(_resources()["https://acme.test/js/app.js"], status=200)
    assert result.bucket == "ok"
    assert result.priority is None
    assert result.reason == ""


def test_unverifiable_resource_does_not_get_a_broken_reason():
    """A 403 on an image proves nothing — do not tell the client it is broken."""
    result = _check(_resources()["https://acme.test/img/broken.png"], status=403)
    assert result.bucket == "unverifiable"
    assert "Broken" not in (result.reason or "")


# ─── overview panels ─────────────────────────────────────────────────────────
def _rows():
    soup = BeautifulSoup(FIXTURE, "lxml")
    rows = collect_resources(soup, PAGE)
    from models import RawLink
    rows.append(RawLink(url="https://acme.test/about", source_element="a",
                        anchor_text="About", category="Body text", is_external=False))
    rows.append(RawLink(url="mailto:hi@acme.test", source_element="a", anchor_text="Mail",
                        category="Footer", is_external=False, link_kind="contact"))
    return rows


def test_link_type_breakdown_counts_each_type():
    counts = link_type_breakdown(_rows())
    assert counts[SCRIPT] == 1
    assert counts[STYLESHEET] == 1
    assert counts[IFRAME] == 1
    assert counts["anchor"] == 2       # the <a> and the mailto row
    assert counts[CSS_URL] == 3        # hero.jpg, extra.css, inline.png


def test_scheme_breakdown():
    schemes = scheme_breakdown(_rows())
    assert schemes["https"] >= 10
    assert schemes["mailto"] == 1


def test_host_breakdown_is_ranked_and_skips_hostless_urls():
    hosts = host_breakdown(_rows())
    assert hosts[0]["host"] == "acme.test"
    assert all(h["host"] for h in hosts)
    assert hosts == sorted(hosts, key=lambda h: (-h["count"], h["host"]))


def test_host_breakdown_respects_limit():
    assert len(host_breakdown(_rows(), limit=1)) == 1
