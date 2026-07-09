"""
Astro is static-first, not an SPA: it ships literal HTML, so its markup is
analyzed at full confidence. The exception is <astro-island> / <astro-slot>
subtrees, which are hydrated by JS at runtime — a dead-looking element in
there may well get a listener attached, so it degrades to low / unverifiable.
"""
from bs4 import BeautifulSoup

from dead_cta_detector import find_dead_ctas, detect_builders


URL = "https://astro.test/"

ASTRO_FIXTURE = """
<!doctype html>
<html>
<head><meta name="generator" content="Astro v5"></head>
<body>
  <!-- (a) static section: analyzable at full confidence -->
  <section class="static">
    <a href="#" class="btn">Get Started</a>
  </section>

  <!-- (b) identical button, but JS-hydrated -->
  <astro-island component-url="/_astro/Counter.js">
    <button class="btn">Get Started</button>
  </astro-island>

  <!-- (c) placeholder link never wired up -->
  <a href="https://example.com" class="btn">Book Now</a>

  <!-- (d) valid static anchor to an id that exists -->
  <a href="#features">See Features</a>
  <section id="features"><h2>Features</h2></section>
</body>
</html>
"""


def _flags():
    soup = BeautifulSoup(ASTRO_FIXTURE, "lxml")
    return soup, find_dead_ctas(soup, URL)


def test_astro_is_detected_as_a_builder():
    soup = BeautifulSoup(ASTRO_FIXTURE, "lxml")
    assert any(b["name"] == "Astro" for b in detect_builders(soup))


def test_astro_is_not_treated_as_an_spa():
    """A static Astro anchor keeps full confidence — proof Astro isn't an SPA marker."""
    _, flags = _flags()
    static = next(f for f in flags if f.source_element == "a" and f.anchor_text == "Get Started")
    assert static.confidence == "high"


def test_static_section_dead_cta_flags_high_dead_cta():
    _, flags = _flags()
    static = next(f for f in flags if f.source_element == "a" and f.anchor_text == "Get Started")
    assert static.confidence == "high"
    assert static.bucket == "dead_cta"


def test_hydration_island_dead_cta_flags_low_unverifiable():
    _, flags = _flags()
    island = next(f for f in flags if f.source_element == "button" and f.anchor_text == "Get Started")
    assert island.confidence == "low"
    assert island.bucket == "unverifiable"


def test_placeholder_link_flags_high_dead_cta():
    _, flags = _flags()
    book = next(f for f in flags if f.anchor_text == "Book Now")
    assert book.confidence == "high"
    assert book.bucket == "dead_cta"
    assert "placeholder" in book.reason.lower()


def test_valid_static_anchor_does_not_flag():
    _, flags = _flags()
    assert "See Features" not in {f.anchor_text for f in flags}


def test_astro_reason_names_the_builder():
    _, flags = _flags()
    assert flags, "expected flags"
    for f in flags:
        assert "Astro" in f.reason, f.reason


def test_placeholder_inside_hydration_island_stays_high():
    """An island degrades a *handler* inference (JS may attach a listener), but
    a link to example.com is a content defect hydration cannot fix."""
    html = (
        '<html><head><meta name="generator" content="Astro v5"></head><body>'
        '<astro-island><a href="https://example.com" class="btn">Book Now</a></astro-island>'
        "</body></html>"
    )
    flags = find_dead_ctas(BeautifulSoup(html, "lxml"), URL)
    book = next(f for f in flags if f.anchor_text == "Book Now")
    assert book.confidence == "high"
    assert book.bucket == "dead_cta"


def test_placeholder_path_marker_is_flagged():
    """Placeholder markers are matched on host *and* path (e.g. /yourhandle)."""
    html = '<html><body><a href="https://twitter.com/yourhandle" class="btn">Follow Us</a></body></html>'
    flags = find_dead_ctas(BeautifulSoup(html, "lxml"), URL)
    follow = next(f for f in flags if f.anchor_text == "Follow Us")
    assert follow.confidence == "high"
    assert follow.bucket == "dead_cta"
    assert "placeholder" in follow.reason.lower()
