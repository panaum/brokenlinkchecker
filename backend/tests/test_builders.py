"""
Per-builder tests: each snippet contains the builder's detect marker, 1-3
builder-idiomatic working elements that must NOT flag, and exactly ONE genuinely
dead CTA (href="#", no evidence). Asserts the builder is detected, the flagged
set is exactly the one dead CTA, and every reason names the builder.
"""
import pytest
from bs4 import BeautifulSoup

from dead_cta_detector import find_dead_ctas, detect_builders


URL = "https://site.test/"
DEAD = '<a href="#" class="promo-btn">Ghost CTA</a>'


def _wrap(body):
    return f"<!doctype html><html><body>{body}</body></html>"


# name, body-html, expect_all_low
BUILDER_CASES = [
    ("Elementor",
     '<a href="#elementor-action:action=popup&settings=abc" class="elementor-button">Open Popup</a>' + DEAD,
     False),
    ("Divi",
     '<section class="et_pb_section et-db"><a href="#" class="et_pb_toggle_title">Toggle</a></section>' + DEAD,
     False),
    ("WPBakery",
     '<div class="vc_row js_composer"><a href="#" class="vc_tta-panel-title">Panel</a></div>' + DEAD,
     False),
    ("Beaver Builder",
     '<div class="fl-builder"><a href="#" class="fl-menu-toggle">Menu</a></div>' + DEAD,
     False),
    ("Bricks",
     '<a href="#" class="brxe-accordion__title">Item</a>' + DEAD,
     False),
    ("Oxygen",
     '<div class="ct-section"><a href="#" class="oxy-toggle">Toggle</a></div>' + DEAD,
     False),
    ("Brizy",
     '<a href="#" class="brz-menu__item">Menu</a>' + DEAD,
     False),
    ("Gutenberg",
     '<a href="#" class="wp-block-navigation__link">Nav</a>' + DEAD,
     False),
    ("Webflow",
     '<div class="webflow" data-wf-page="p"><a href="#" data-w-id="abc123">Toggle</a></div>' + DEAD,
     False),
    ("Wix",
     '<script src="https://static.parastorage.com/x.js"></script>'
     '<button aria-haspopup="true">Menu</button>' + DEAD,
     True),
    ("Squarespace",
     '<script src="https://static1.squarespace.com/x.js"></script>'
     '<a href="#" class="header-burger">Menu</a>' + DEAD,
     False),
    ("Unbounce",
     '<div id="lp-pom-form"></div><a href="#lp-pom-form">Sign Up</a>' + DEAD,
     False),
    ("ClickFunnels",
     '<div class="containerWrapper" data-page-element="x">'
     '<a href="#submit-form" class="elButton">Order Now</a></div>' + DEAD,
     False),
    ("GoHighLevel",
     '<script src="https://x.msgsndr.com/y.js"></script>'
     '<a href="#popup-9f8e7d">Book Now</a>' + DEAD,
     False),
    ("Leadpages",
     '<script src="https://x.lpages.co/y.js"></script>'
     '<a href="#" data-leadbox="abc">Open</a>' + DEAD,
     False),
    ("Instapage",
     '<div class="instapage-page"><a href="#element-42">Scroll</a></div>' + DEAD,
     False),
    ("Kajabi",
     '<div class="kajabi-theme"><a href="#" class="kjb-slider__arrow">Arrow</a></div>' + DEAD,
     False),
    ("HubSpot CMS",
     '<script src="https://js.hs-scripts.com/123.js"></script>'
     '<a href="#" data-hs-cta-tracking="123">CTA</a>' + DEAD,
     False),
    ("Shopify",
     '<script src="https://cdn.shopify.com/x.js"></script>'
     '<button class="shopify-payment-button__button">Buy</button>' + DEAD,
     False),
    ("Framer",
     '<div data-framer-name="Hero">Framed</div>'
     '<img src="https://framerusercontent.com/x.png">'
     '<button aria-haspopup="true">Menu</button>' + DEAD,
     True),
    ("Duda",
     '<meta name="generator" content="Duda"><a href="#" class="dmnav-item">Menu</a>' + DEAD,
     False),
    ("Carrd",
     '<meta name="generator" content="Carrd"><button aria-haspopup="true">Menu</button>' + DEAD,
     True),
    ("Astro",
     '<meta name="generator" content="Astro v5"><button aria-controls="m">Menu</button><div id="m"></div>' + DEAD,
     False),
    ("Hugo",
     '<meta name="generator" content="Hugo 0.120.4"><button aria-controls="m">Menu</button><div id="m"></div>' + DEAD,
     False),
    ("Jekyll",
     '<meta name="generator" content="Jekyll v4.3.2"><button aria-controls="m">Menu</button><div id="m"></div>' + DEAD,
     False),
    ("Eleventy",
     '<meta name="generator" content="Eleventy v2.0.1"><button aria-controls="m">Menu</button><div id="m"></div>' + DEAD,
     False),
]


@pytest.mark.parametrize("name,body,expect_low", BUILDER_CASES, ids=[c[0] for c in BUILDER_CASES])
def test_builder(name, body, expect_low):
    soup = BeautifulSoup(_wrap(body), "lxml")

    # 1. builder detected
    assert any(b["name"] == name for b in detect_builders(soup)), \
        f"{name} not detected"

    flags = find_dead_ctas(soup, URL)
    texts = {f.anchor_text for f in flags}

    # 2. flagged set == the one genuinely dead CTA
    assert texts == {"Ghost CTA"}, f"{name}: {texts}"

    # 3. every reason names the builder
    for f in flags:
        assert name in f.reason, f"{name} missing from reason: {f.reason!r}"

    # 4. SPA builders (Wix, Framer, Carrd) can't be judged from static HTML:
    #    everything degrades to low confidence / unverifiable. Static builders
    #    keep the CTA-classed dead link at high confidence / dead_cta.
    if expect_low:
        assert all(f.confidence == "low" for f in flags), \
            [(f.anchor_text, f.confidence) for f in flags]
        assert all(f.bucket == "unverifiable" for f in flags), \
            [(f.anchor_text, f.bucket) for f in flags]
    else:
        ghost = next(f for f in flags if f.anchor_text == "Ghost CTA")
        assert ghost.confidence == "high", ghost.confidence
        assert ghost.bucket == "dead_cta", ghost.bucket


# ─────────────────────────────────────────────────────────────────────────────
# Regression (found by scripts/validate_live.py against https://astro.build):
# bare vendor-name detect markers matched a *mention* of the builder rather than
# its use — a customer-logo SVG (aria-label="webflow"), an Astro theme named
# "astro-shopify", a comparison paragraph, a link to a vendor's homepage. Each
# misattribution also merged that builder's widget hints into suppression, which
# can silently hide genuinely dead CTAs.
# ─────────────────────────────────────────────────────────────────────────────
MENTIONS_ONLY = """
<!doctype html>
<html>
<head><meta name="generator" content="Astro v5"></head>
<body>
  <svg aria-label="webflow" data-icon="logos/webflow"><symbol id="ai:local:logos/webflow"></symbol></svg>
  <a href="/themes/details/astro-shopify/">
    <img src="/_astro/astro-shopify.b2calq31.webp" alt="astro shopify theme by thomaskn">
  </a>
  <p>Migrating from Squarespace or Wix? We also compare Hugo, Jekyll and Eleventy.</p>
  <a href="https://www.squarespace.com">Squarespace</a>
  <a href="https://kajabi.com">Kajabi</a>
  <a href="https://instapage.com">Instapage</a>
</body>
</html>
"""


def test_vendor_mentions_do_not_detect_builders():
    soup = BeautifulSoup(MENTIONS_ONLY, "lxml")
    detected = {b["name"] for b in detect_builders(soup)}
    assert detected == {"Astro"}, f"misdetected from mere mentions: {detected - {'Astro'}}"


@pytest.mark.parametrize("name,markup", [
    ("Webflow", '<svg aria-label="webflow" data-icon="logos/webflow"></svg>'),
    ("Shopify", '<a href="/themes/details/astro-shopify/">astro shopify theme</a>'),
    ("Squarespace", '<a href="https://www.squarespace.com">Squarespace</a>'),
    ("Kajabi", '<a href="https://kajabi.com">Kajabi</a>'),
    ("Instapage", '<a href="https://instapage.com">Instapage</a>'),
    ("Hugo", "<p>Our founder Hugo wrote this.</p>"),
    ("Duda", "<p>No hay duda: it works.</p>"),
    ("Carrd", "<p>We support Carrd imports.</p>"),
])
def test_single_vendor_mention_does_not_detect(name, markup):
    soup = BeautifulSoup(_wrap(markup), "lxml")
    detected = {b["name"] for b in detect_builders(soup)}
    assert name not in detected


# ─────────────────────────────────────────────────────────────────────────────
# Regression (found by scripts/validate_live.py against https://www.allbirds.com):
# the Oxygen marker "ct-section" matched inside "use-produ|ct-section-visibility.js",
# reporting a Shopify store as Oxygen. Detect markers that begin with a word
# character must start at a token boundary.
# ─────────────────────────────────────────────────────────────────────────────
def test_product_section_asset_does_not_detect_oxygen():
    html = _wrap(
        '<link rel="modulepreload" '
        'href="//www.allbirds.com/cdn/shop/t/4148/assets/use-product-section-visibility.js">'
    )
    detected = {b["name"] for b in detect_builders(BeautifulSoup(html, "lxml"))}
    assert "Oxygen" not in detected


def test_real_oxygen_section_still_detected():
    html = _wrap('<div class="ct-section"><div class="ct-section-inner-wrap"></div></div>')
    detected = {b["name"] for b in detect_builders(BeautifulSoup(html, "lxml"))}
    assert "Oxygen" in detected


def test_punctuation_initial_marker_still_matches_after_word_char():
    """`/cdn/shop/` is preceded by "…allbirds.com" — the boundary guard must not
    apply to markers that begin with punctuation, or Shopify stops detecting."""
    html = _wrap('<img src="//www.allbirds.com/cdn/shop/files/hero.png">')
    detected = {b["name"] for b in detect_builders(BeautifulSoup(html, "lxml"))}
    assert "Shopify" in detected


def test_kajabi_cdn_asset_host_detects_kajabi():
    """Real Kajabi infra: kajabi-app-assets.kajabi-cdn.com (preceded by a dot)."""
    html = _wrap('<script src="https://kajabi-app-assets.kajabi-cdn.com/landers-service.js"></script>')
    detected = {b["name"] for b in detect_builders(BeautifulSoup(html, "lxml"))}
    assert "Kajabi" in detected


def test_every_builder_profile_has_a_test_case():
    """Guard against adding a profile in B5 without a matching test snippet."""
    from dead_cta_detector import BUILDER_PROFILES

    covered = {c[0] for c in BUILDER_CASES}
    declared = {p["name"] for p in BUILDER_PROFILES}
    assert declared == covered, f"untested: {declared - covered}, stale: {covered - declared}"


# ─────────────────────────────────────────────────────────────────────────────
# Regression (found generating a real Fix Pack for apexure.com, a landing-page
# agency): bare vendor markers matched the agency's own MARKETING COPY and a
# link in its nav —
#     "...high converting landing pages, unbounce landing pages..."
#     <a href="/framer-development-agency/">
# The site is neither Unbounce nor Framer, and the Fix Pack rendered Unbounce
# instructions for it. Wrong instructions on a live page are the one thing this
# feature must never do.
# ─────────────────────────────────────────────────────────────────────────────
AGENCY_COPY = """
<!doctype html><html><body>
  <script type="application/ld+json">
    {"keywords": "high converting landing pages, unbounce landing pages"}
  </script>
  <p>Partnered with Headway managing 50+ unbounce pages and marketo forms.</p>
  <nav><a href="/framer-development-agency/">Framer development</a></nav>
  <a href="/unbounce-landing-pages/">Unbounce landing pages</a>
</body></html>
"""


def test_an_agency_writing_about_builders_is_not_built_with_them():
    detected = {b["name"] for b in detect_builders(BeautifulSoup(AGENCY_COPY, "lxml"))}
    assert "Unbounce" not in detected
    assert "Framer" not in detected


def test_a_real_unbounce_page_is_still_detected():
    html = _wrap('<div id="lp-pom-root"><div class="lp-pom-block"></div></div>')
    detected = {b["name"] for b in detect_builders(BeautifulSoup(html, "lxml"))}
    assert "Unbounce" in detected


def test_a_real_framer_page_is_still_detected():
    html = _wrap('<div data-framer-name="Hero"></div>'
                 '<img src="https://framerusercontent.com/x.png">')
    detected = {b["name"] for b in detect_builders(BeautifulSoup(html, "lxml"))}
    assert "Framer" in detected
