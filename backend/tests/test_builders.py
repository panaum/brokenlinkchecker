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
     '<div class="framer-abc123">Framed</div>'
     '<button aria-haspopup="true">Menu</button>' + DEAD,
     True),
    ("Duda",
     '<meta name="generator" content="Duda"><a href="#" class="dmnav-item">Menu</a>' + DEAD,
     False),
    ("Carrd",
     '<meta name="generator" content="Carrd"><button aria-haspopup="true">Menu</button>' + DEAD,
     False),
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

    # 4. SPA builders => all flags low confidence
    if expect_low:
        assert all(f.confidence == "low" for f in flags), \
            [(f.anchor_text, f.confidence) for f in flags]
