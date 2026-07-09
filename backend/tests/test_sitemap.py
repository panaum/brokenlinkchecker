"""
Fallback crawler.

Regression: scrape_links grew a return value (links, builders, signals), but
crawl_site still unpacked it as a plain list. `raw_link.url` then raised
AttributeError inside a broad `except`, so the crawl silently discovered nothing
beyond the homepage — a scan that looked like it worked.
"""
import asyncio

import pytest

import sitemap
from models import RawLink


BASE = "https://acme.test/"


def _anchor(url, external=False) -> RawLink:
    return RawLink(url=url, source_element="a", anchor_text="x",
                   category="Body text", is_external=external)


def _resource(url, rtype) -> RawLink:
    return RawLink(url=url, source_element=rtype, anchor_text=rtype,
                   category="Resource", is_external=False, resource_type=rtype)


PAGE_LINKS = [
    _anchor("https://acme.test/about"),
    _anchor("https://acme.test/pricing"),
    _anchor("https://other.test/partner", external=True),
    # These must never be crawled as pages.
    _resource("https://acme.test/js/app.js", "script"),
    _resource("https://acme.test/img/logo.png", "image"),
    _resource("https://acme.test/css/site.css", "stylesheet"),
]


@pytest.fixture
def stub_scrape(monkeypatch):
    calls = []

    async def fake_scrape(url):
        calls.append(url)
        # Only the homepage links onward; deeper pages are leaves.
        return (PAGE_LINKS if url == BASE else [], ["Astro"], {})

    monkeypatch.setattr(sitemap, "scrape_links", fake_scrape)
    return calls


def test_crawl_discovers_internal_pages(stub_scrape):
    found = asyncio.run(sitemap.crawl_site(BASE, max_pages=10))
    assert "https://acme.test/about" in found
    assert "https://acme.test/pricing" in found


def test_crawl_does_not_enqueue_assets_as_pages(stub_scrape):
    """Scripts, images and stylesheets are resources, not pages."""
    found = asyncio.run(sitemap.crawl_site(BASE, max_pages=10))
    for asset in ("app.js", "logo.png", "site.css"):
        assert not any(asset in url for url in found), asset


def test_crawl_skips_external_links(stub_scrape):
    found = asyncio.run(sitemap.crawl_site(BASE, max_pages=10))
    assert not any("other.test" in url for url in found)


def test_crawl_respects_max_pages(stub_scrape):
    found = asyncio.run(sitemap.crawl_site(BASE, max_pages=2))
    assert len(found) <= 2


def test_crawl_survives_a_failing_page(monkeypatch):
    async def boom(url):
        raise RuntimeError("navigation failed")

    monkeypatch.setattr(sitemap, "scrape_links", boom)
    found = asyncio.run(sitemap.crawl_site(BASE, max_pages=5))
    # The base URL is always in the set; a crash must not return nothing.
    assert found == [BASE]
