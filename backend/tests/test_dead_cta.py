"""
Dead-CTA detection tests — pure functions against static HTML fixtures.
No Playwright required.
"""
from bs4 import BeautifulSoup

from dead_cta_detector import find_dead_ctas


URL = "https://acme.test/"


# ─────────────────────────────────────────────────────────────────────────────
# Main fixture: TRUE dead CTAs mixed with working JS-driven / declarative UI.
# ─────────────────────────────────────────────────────────────────────────────
MAIN_FIXTURE = """
<!doctype html>
<html>
<head><title>Fixture</title></head>
<body>
  <!-- ===== TRUE DEAD CTAs (must flag) ===== -->
  <a href="#" class="btn">Buy Now</a>
  <a class="cta-button">Get Started Free</a>
  <a href="javascript:void(0)">Order Now</a>
  <a href="">Download Brochure</a>
  <a href="#!">Start Trial</a>
  <div><button class="signup-btn">Sign Up Today</button></div>
  <a href="#testimonials">See Testimonials</a>

  <!-- ===== WORKING ELEMENTS (must NOT flag) ===== -->
  <nav>
    <ul>
      <li class="menu-item">
        <a href="#">Products</a>
        <ul><li><a href="/p1">P1</a></li></ul>
      </li>
    </ul>
  </nav>
  <button class="hamburger" aria-controls="mobile-menu" aria-expanded="false">Menu</button>
  <div id="mobile-menu"></div>
  <button role="tab">Features</button>
  <button role="tab">Pricing Tab</button>
  <a href="#" class="swiper-button-next">Next</a>
  <a href="#" class="swiper-button-prev">Prev</a>
  <a href="#" class="slick-prev">Slick Prev</a>
  <a href="#" class="slick-next">Slick Next</a>
  <button class="accordion-header" aria-expanded="false">FAQ Item</button>
  <button data-bs-toggle="modal" data-bs-target="#myModal">Open Modal</button>
  <div id="myModal"></div>
  <a href="#elementor-action:action=popup&settings=abc">Special Offer</a>
  <a href="#" onclick="openThing()">Learn</a>
  <a href="#" class="btn" data-gtm-event="cta">Track Me</a>
  <div role="button" class="cookie-consent-accept">Accept Cookies</div>
  <form><button>Submit Form</button></form>
  <section id="pricing"><h2>Pricing</h2></section>
  <a href="#pricing">See Pricing</a>
  <a href="#top" class="back-to-top">Top</a>
  <a href="tel:+15551234567">Call Us</a>
  <a href="mailto:hi@acme.test">Email Us</a>
  <a href="#" class="btn" data-js-listener="1">Stamped CTA</a>
  <div class="pricing-table"><a href="/pricing">Compare Plans</a></div>
</body>
</html>
"""

TRUE_DEAD = {
    "Buy Now",
    "Get Started Free",
    "Order Now",
    "Download Brochure",
    "Start Trial",
    "Sign Up Today",
    "See Testimonials",
}

# CTA-classed / CTA-verb dead links that must come back HIGH confidence.
HIGH_CONFIDENCE_DEAD = {
    "Buy Now",
    "Get Started Free",
    "Order Now",
    "Download Brochure",
    "Start Trial",
    "Sign Up Today",
}


def _soup(html):
    return BeautifulSoup(html, "lxml")


def test_flagged_set_exactly_matches_true_dead():
    flags = find_dead_ctas(_soup(MAIN_FIXTURE), URL)
    flagged = {f.anchor_text for f in flags}
    assert flagged == TRUE_DEAD, (
        f"unexpected: {flagged - TRUE_DEAD}, missing: {TRUE_DEAD - flagged}"
    )


def test_cta_classed_dead_links_are_high_confidence():
    flags = {f.anchor_text: f for f in find_dead_ctas(_soup(MAIN_FIXTURE), URL)}
    for text in HIGH_CONFIDENCE_DEAD:
        assert flags[text].confidence == "high", f"{text} -> {flags[text].confidence}"


def test_cta_classed_dead_links_are_bucket_dead_cta():
    flags = {f.anchor_text: f for f in find_dead_ctas(_soup(MAIN_FIXTURE), URL)}
    for text in HIGH_CONFIDENCE_DEAD:
        assert flags[text].bucket == "dead_cta", f"{text} -> {flags[text].bucket}"


def test_every_flag_carries_a_reason():
    for f in find_dead_ctas(_soup(MAIN_FIXTURE), URL):
        assert f.reason.strip(), f"{f.anchor_text} has no reason"


def test_broken_in_page_anchor_reason_names_fragment():
    flags = {f.anchor_text: f for f in find_dead_ctas(_soup(MAIN_FIXTURE), URL)}
    assert "testimonials" in flags["See Testimonials"].reason.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Regression: the "tab"/"table" guard. Without stripping the substring "table"
# from the class blob, the widget keyword "tab" matches "pricing-table" and
# suppresses every dead CTA nested inside a pricing table (a false negative).
# ─────────────────────────────────────────────────────────────────────────────
def test_pricing_table_does_not_suppress_nested_dead_cta():
    html = (
        '<html><body><div class="pricing-table">'
        '<a href="#" class="btn">Buy Now</a>'
        '</div></body></html>'
    )
    flags = {f.anchor_text for f in find_dead_ctas(_soup(html), URL)}
    assert "Buy Now" in flags


def test_real_tab_widget_still_suppressed():
    html = (
        '<html><body><div class="tab-panel">'
        '<a href="#" class="btn">Buy Now</a>'
        '</div></body></html>'
    )
    flags = {f.anchor_text for f in find_dead_ctas(_soup(html), URL)}
    assert "Buy Now" not in flags


# ─────────────────────────────────────────────────────────────────────────────
# Legacy logic snapshot — documents the false positives we protect against.
# This is a faithful copy of the pre-refactor _find_dead_ctas.
# ─────────────────────────────────────────────────────────────────────────────
_LEGACY_DEAD_HREFS = {
    "", "#", "#0", "#!", "#null", "#undefined",
    "javascript:", "javascript:void(0)", "javascript:void(0);",
    "javascript:;", "javascript:return false;",
    "javascript:return false", "javascript:null",
    "void(0)", "#link", "#anchor",
}
_LEGACY_CTA_KEYWORDS = [
    "btn", "button", "cta", "call-to-action", "action", "signup", "sign-up",
    "register", "get-started", "getstarted", "try-free", "start-free",
    "learn-more", "learnmore", "buy-now", "buynow", "order-now", "ordernow",
    "subscribe", "download", "free-trial", "book-demo", "bookdemo",
    "contact-us", "hero__cta", "primary", "secondary",
]


def _legacy_is_dead_href(href):
    if not href:
        return True
    href = href.strip().lower()
    if href in _LEGACY_DEAD_HREFS:
        return True
    if href.startswith("javascript:"):
        return True
    if href == "#" or (href.startswith("#") and len(href) <= 2):
        return True
    return False


def _legacy_has_cta_class(tag):
    classes = tag.get("class", [])
    if isinstance(classes, str):
        classes = classes.split()
    class_str = " ".join(classes).lower()
    return any(k in class_str for k in _LEGACY_CTA_KEYWORDS)


def legacy_find_dead_ctas(soup):
    dead = []
    seen = set()
    for tag in soup.find_all("a"):
        href = tag.get("href", "").strip()
        if not _legacy_is_dead_href(href):
            continue
        anchor = (tag.get_text(strip=True) or "")[:80]
        key = f"{anchor}_{href}"
        if key in seen:
            continue
        seen.add(key)
        dead.append(anchor or "[no text]")
    for tag in soup.find_all("button"):
        onclick = tag.get("onclick", "").strip().lower()
        tag_type = tag.get("type", "button").lower()
        if tag_type in ["submit", "reset"]:
            continue
        if onclick and not any(d in onclick for d in ["void(0)", "return false", "javascript:", "#"]):
            continue
        anchor = (tag.get_text(strip=True) or "")[:80]
        key = f"btn_{anchor}_{onclick}"
        if key in seen:
            continue
        seen.add(key)
        dead.append(anchor or "[no text]")
    for tag_name in ["div", "span", "li"]:
        for tag in soup.find_all(tag_name):
            role = tag.get("role", "").lower()
            onclick = tag.get("onclick", "").strip().lower()
            is_button_role = role == "button"
            has_cta_cls = _legacy_has_cta_class(tag)
            has_dead_onclick = onclick and any(d in onclick for d in ["void(0)", "return false", "#"])
            has_no_action = is_button_role and not onclick
            if not (is_button_role or (has_cta_cls and (has_dead_onclick or has_no_action))):
                continue
            anchor = (tag.get_text(strip=True) or "")[:80]
            if len(anchor) > 50:
                continue
            key = f"div_{anchor}_{onclick}"
            if key in seen:
                continue
            seen.add(key)
            dead.append(anchor or "[no text]")
    return dead


def test_legacy_logic_produces_many_false_positives():
    legacy = legacy_find_dead_ctas(_soup(MAIN_FIXTURE))
    false_positives = [a for a in legacy if a not in TRUE_DEAD]
    assert len(false_positives) >= 12, f"only {len(false_positives)}: {false_positives}"


def test_new_logic_has_zero_false_positives_vs_legacy():
    new_flags = {f.anchor_text for f in find_dead_ctas(_soup(MAIN_FIXTURE), URL)}
    assert new_flags.issubset(TRUE_DEAD)


# ─────────────────────────────────────────────────────────────────────────────
# SPA fixture: every flag must be low confidence.
# ─────────────────────────────────────────────────────────────────────────────
SPA_FIXTURE = """
<!doctype html>
<html>
<body>
  <div id="root" data-reactroot="">
    <a href="#" class="btn">Buy Now</a>
    <div><button class="cta">Sign Up</button></div>
  </div>
</body>
</html>
"""


def test_spa_flags_are_all_low_confidence():
    flags = find_dead_ctas(_soup(SPA_FIXTURE), URL)
    assert flags, "expected some flags in the SPA fixture"
    assert all(f.confidence == "low" for f in flags), [
        (f.anchor_text, f.confidence) for f in flags
    ]


def test_spa_flags_are_all_unverifiable():
    flags = find_dead_ctas(_soup(SPA_FIXTURE), URL)
    assert flags, "expected some flags in the SPA fixture"
    assert all(f.bucket == "unverifiable" for f in flags), [
        (f.anchor_text, f.bucket) for f in flags
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Regression: builder "theme" body classes must NOT suppress the whole page.
# (et_divi_theme / kajabi-theme contain the substring "theme" but not "theme-".)
# ─────────────────────────────────────────────────────────────────────────────
def test_divi_theme_body_class_does_not_suppress_page():
    html = (
        '<html><body class="et_divi_theme et-db">'
        '<section class="et_pb_section"><a href="#" class="et_pb_toggle_title">Toggle</a></section>'
        '<a href="#" class="promo-btn">Ghost CTA</a>'
        '</body></html>'
    )
    flags = {f.anchor_text for f in find_dead_ctas(_soup(html), URL)}
    assert "Ghost CTA" in flags          # page not globally suppressed
    assert "Toggle" not in flags         # real Divi toggle still suppressed


def test_kajabi_theme_body_class_does_not_suppress_page():
    html = (
        '<html><body class="kajabi-theme">'
        '<a href="#" class="kjb-slider__arrow">Arrow</a>'
        '<a href="#" class="promo-btn">Ghost CTA</a>'
        '</body></html>'
    )
    flags = {f.anchor_text for f in find_dead_ctas(_soup(html), URL)}
    assert "Ghost CTA" in flags          # page not globally suppressed
    assert "Arrow" not in flags          # real Kajabi slider arrow still suppressed
