"""
Link collection: one row per unique destination, every occurrence accounted for.

Covers the three link kinds a visitor can see on a page — http(s) links,
in-page #anchors, and mailto:/tel: contacts — so nothing a user can count by
eye is silently dropped.

Pure function tests against static HTML — no Playwright.
"""
from bs4 import BeautifulSoup

from scraper import _collect_links


URL = "https://site.test/"


FIXTURE = """
<!doctype html>
<html><body>
  <nav>
    <a href="/about-us/">About</a>
    <a href="/careers/">Careers</a>
    <a href="#services">Services</a>
    <a href="/#reviews">Reviews</a>
  </nav>

  <main>
    <p><a href="/about-us/">more about us</a></p>
    <a href="https://external.example/partner">Partner</a>
    <a href="#nowhere">Broken anchor</a>
  </main>

  <section id="services">Services</section>

  <footer>
    <a href="/about-us/">About</a>
    <a href="/careers/">Careers</a>
    <a href="/privacy-policy/">Privacy</a>
    <a href="/accessibility/">Accessibility</a>
    <a href="#top">Back to top</a>
    <a href="mailto:hi@site.test">Email</a>
    <a href="tel:+15551234567">Call</a>
    <a href="javascript:void(0)">Noop</a>
  </footer>
</body></html>
"""


def _rows():
    soup = BeautifulSoup(FIXTURE, "lxml")
    return _collect_links(soup, URL)


def _by_url():
    return {r.url: r for r in _rows()}


def _kinds():
    out = {}
    for r in _rows():
        out.setdefault(r.link_kind, []).append(r)
    return out


# ─── link kinds ──────────────────────────────────────────────────────────────
def test_in_page_anchor_is_not_fetched_over_http():
    """`#services` must not become "https://site.test/#services" and get fetched.
    HTTP never sees the fragment, so the request just re-downloads the page."""
    services = _by_url()["https://site.test/#services"]
    assert services.link_kind == "anchor"
    assert services.fragment == "services"


def test_implicit_top_anchor_is_valid():
    assert _by_url()["https://site.test/#top"].link_kind == "anchor"


def test_unresolved_anchor_is_left_to_the_dead_cta_detector():
    """`#nowhere` has no target. The detector reports it (with its suppression
    rules); listing it here as well would double-report the same defect."""
    assert not any(r.fragment == "nowhere" for r in _rows())


def test_mailto_and_tel_are_contact_links():
    contacts = {r.url for r in _kinds()["contact"]}
    assert contacts == {"mailto:hi@site.test", "tel:+15551234567"}


def test_javascript_href_is_not_a_link():
    assert not any("javascript" in r.url for r in _rows())


def test_path_with_fragment_is_an_http_link_carrying_its_fragment():
    """`/#reviews` is a real HTTP destination; the fragment is checked separately."""
    row = _by_url()["https://site.test/#reviews"]
    assert row.link_kind == "http"
    assert row.fragment == "reviews"


# ─── occurrence + zone merging ───────────────────────────────────────────────
def test_url_in_nav_and_footer_is_one_row_with_both_zones():
    about = _by_url()["https://site.test/about-us/"]
    assert sorted(about.zones) == ["Body text", "Footer", "Navigation"]
    assert about.occurrences == 3


def test_primary_category_is_the_highest_priority_zone():
    """Navigation (critical) outranks Footer and Body text (both medium)."""
    assert _by_url()["https://site.test/about-us/"].category == "Navigation"
    assert _by_url()["https://site.test/careers/"].category == "Navigation"


def test_footer_exclusive_links_are_attributed_to_the_footer():
    rows = _by_url()
    for path in ("privacy-policy", "accessibility"):
        row = rows[f"https://site.test/{path}/"]
        assert row.category == "Footer", (path, row.category)
        assert row.zones == ["Footer"]


def test_every_unique_destination_appears_exactly_once():
    rows = _rows()
    assert len(rows) == len({r.url for r in rows})


def test_occurrences_account_for_every_visible_link():
    rows = _rows()
    # http:    nav(about, careers, /#reviews) + main(about, partner)
    #          + footer(about, careers, privacy, accessibility)      = 9
    # anchor:  #services, #top                                        = 2
    # contact: mailto, tel                                            = 2
    # skipped: #nowhere (dead-CTA detector), javascript:void(0)
    assert sum(r.occurrences for r in rows) == 13
    assert len(rows) == 10


def test_relative_hrefs_resolve_against_the_page_url():
    assert "https://site.test/careers/" in _by_url()


def test_external_flag_only_applies_to_http_links():
    rows = _by_url()
    assert rows["https://external.example/partner"].is_external is True
    assert rows["https://site.test/about-us/"].is_external is False
    assert rows["mailto:hi@site.test"].is_external is False


def test_zones_never_empty():
    for row in _rows():
        assert row.zones, row.url
