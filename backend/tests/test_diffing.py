"""
Fingerprint stability and snapshot diffing.

If a fingerprint is unstable, every downstream feature inherits the bug: issues
look new forever, ages reset each scan, and nothing is ever reported as fixed.
"""
import pytest

from diffing import (
    age_phrase,
    collect_findings,
    diff_findings,
    diff_link_counts,
    diff_status_by_fingerprint,
    finding_fingerprint,
    issue_age_days,
    link_fingerprints,
    normalize_anchor_text,
    normalize_url,
    summarize_diff,
)
from models import FindingRecord, RawLink


PAGE = "https://acme.test/pricing"


def _fp(page=PAGE, href="https://acme.test/gone", anchor="Buy Now", kind="http"):
    return finding_fingerprint(page, href, anchor, kind)


# ─── normalize_url ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("a,b", [
    # tracking params never change identity
    ("https://acme.test/p?utm_source=x", "https://acme.test/p"),
    ("https://acme.test/p?utm_campaign=a&utm_medium=b", "https://acme.test/p"),
    ("https://acme.test/p?gclid=123", "https://acme.test/p"),
    ("https://acme.test/p?fbclid=1&msclkid=2", "https://acme.test/p"),
    ("https://acme.test/p?hsa_acc=9", "https://acme.test/p"),
    # query order is not identity
    ("https://acme.test/p?b=2&a=1", "https://acme.test/p?a=1&b=2"),
    # case of scheme/host, default ports, trailing slash
    ("HTTPS://ACME.TEST/p", "https://acme.test/p"),
    ("https://acme.test:443/p", "https://acme.test/p"),
    ("http://acme.test:80/p", "http://acme.test/p"),
    ("https://acme.test/p/", "https://acme.test/p"),
    # whitespace
    ("  https://acme.test/p  ", "https://acme.test/p"),
])
def test_normalize_url_collapses_trivial_variations(a, b):
    assert normalize_url(a) == normalize_url(b)


@pytest.mark.parametrize("a,b", [
    # a real query param is identity — must NOT be stripped
    ("https://acme.test/p?id=1", "https://acme.test/p?id=2"),
    ("https://acme.test/p?ref=docs", "https://acme.test/p"),
    ("https://acme.test/p?source=nav", "https://acme.test/p"),
    # different scheme / host / path
    ("https://acme.test/p", "http://acme.test/p"),
    ("https://acme.test/p", "https://other.test/p"),
    ("https://acme.test/a", "https://acme.test/b"),
    ("https://acme.test:8080/p", "https://acme.test/p"),
])
def test_normalize_url_keeps_meaningful_differences(a, b):
    assert normalize_url(a) != normalize_url(b)


def test_root_path_keeps_its_slash():
    assert normalize_url("https://acme.test/") == "https://acme.test/"
    assert normalize_url("https://acme.test") == "https://acme.test/"


def test_page_url_drops_fragment_but_href_keeps_it():
    assert normalize_url("https://acme.test/p#top") == normalize_url("https://acme.test/p")
    assert normalize_url("https://acme.test/p#top", keep_fragment=True) != \
        normalize_url("https://acme.test/p#other", keep_fragment=True)


def test_non_http_schemes_survive_normalization():
    assert normalize_url("MAILTO:Hi@Acme.test") == "mailto:Hi@Acme.test"
    assert normalize_url("tel:+15551234567") == "tel:+15551234567"


def test_normalize_anchor_text():
    assert normalize_anchor_text("  Buy   Now\n") == "buy now"
    assert normalize_anchor_text("BUY NOW") == normalize_anchor_text("buy now")


# ─── fingerprint ─────────────────────────────────────────────────────────────
def test_fingerprint_is_stable_across_reruns():
    assert _fp() == _fp()


def test_fingerprint_is_stable_across_trivial_url_variations():
    base = _fp(page="https://acme.test/pricing", href="https://acme.test/gone")
    assert base == _fp(page="https://acme.test/pricing?utm_source=news",
                       href="https://acme.test/gone")
    assert base == _fp(page="https://acme.test/pricing#top",
                       href="https://acme.test/gone")
    assert base == _fp(page="https://ACME.test/pricing/",
                       href="https://acme.test/gone?gclid=abc")
    assert base == _fp(anchor="  buy   NOW  ")


def test_fingerprint_distinguishes_two_broken_anchors_on_one_page():
    """The href fragment is identity. Collapsing #team and #pricing would make
    one of the two findings permanently invisible."""
    a = _fp(href="https://acme.test/about#team", anchor="Team", kind="http")
    b = _fp(href="https://acme.test/about#pricing", anchor="Pricing", kind="http")
    assert a != b


@pytest.mark.parametrize("kwargs", [
    {"page": "https://acme.test/other"},
    {"href": "https://acme.test/elsewhere"},
    {"anchor": "Different text"},
    {"kind": "anchor"},
])
def test_fingerprint_changes_with_each_identity_component(kwargs):
    assert _fp() != _fp(**kwargs)


def test_fingerprint_is_short_and_hex():
    fp = _fp()
    assert len(fp) == 16
    int(fp, 16)


# ─── collect_findings ────────────────────────────────────────────────────────
def _link(**over) -> RawLink:
    fields = dict(
        url="https://acme.test/gone", source_element="a", anchor_text="Buy Now",
        category="CTA", is_external=False, bucket="broken",
    )
    fields.update(over)
    return RawLink(**fields)


def test_working_links_are_not_findings():
    findings = collect_findings(PAGE, [_link(bucket="ok"), _link(bucket="broken")])
    assert len(findings) == 1
    assert findings[0].bucket == "broken"


def test_findings_are_deduped_by_fingerprint():
    findings = collect_findings(PAGE, [_link(), _link()])
    assert len(findings) == 1


def test_link_fingerprints_include_working_links():
    fps = link_fingerprints(PAGE, [_link(bucket="ok"), _link(bucket="broken", url="https://acme.test/x")])
    assert len(fps) == 2


# ─── diff_findings ───────────────────────────────────────────────────────────
def _finding(fp, bucket="broken", first_seen="2026-07-01T00:00:00+00:00"):
    return FindingRecord(fingerprint=fp, bucket=bucket, url="https://acme.test/x",
                         first_seen_at=first_seen)


NOW = "2026-07-13T00:00:00+00:00"


def test_first_scan_has_no_baseline():
    diff = diff_findings(None, [_finding("aaa")], now=NOW)
    assert diff.has_baseline is False
    assert summarize_diff(diff) == "First scan — no baseline to compare against yet"


def test_two_scan_sequence_yields_new_recurring_fixed():
    previous = [_finding("aaa"), _finding("bbb")]
    current = [_finding("bbb"), _finding("ccc")]
    diff = diff_findings(previous, current, now=NOW)

    assert diff.has_baseline is True
    assert [f.fingerprint for f in diff.new] == ["ccc"]
    assert [f.fingerprint for f in diff.recurring] == ["bbb"]
    assert [f.fingerprint for f in diff.fixed] == ["aaa"]


def test_recurring_finding_keeps_its_original_first_seen_at():
    """Age must survive a rerun, or 'broken for 12 days' resets to zero."""
    previous = [_finding("bbb", first_seen="2026-07-01T00:00:00+00:00")]
    current = [_finding("bbb", first_seen=NOW)]   # this scan's fresh timestamp
    diff = diff_findings(previous, current, now=NOW)
    assert diff.recurring[0].first_seen_at == "2026-07-01T00:00:00+00:00"


def test_fixed_findings_are_stamped_resolved():
    diff = diff_findings([_finding("aaa")], [], now=NOW)
    assert diff.fixed[0].resolved_at == NOW
    assert diff.fixed[0].status == "resolved"


def test_unchanged_page_reports_nothing_new_and_nothing_fixed():
    findings = [_finding("aaa"), _finding("bbb")]
    diff = diff_findings(findings, findings, now=NOW)
    assert diff.new == [] and diff.fixed == []
    assert len(diff.recurring) == 2


def test_summarize_diff_lead_line():
    diff = diff_findings([_finding("a"), _finding("b")], [_finding("b"), _finding("c")], now=NOW)
    assert summarize_diff(diff) == "1 new · 1 fixed · 1 still open"


def test_diff_status_by_fingerprint():
    diff = diff_findings([_finding("b")], [_finding("b"), _finding("c")], now=NOW)
    status = diff_status_by_fingerprint(diff)
    assert status == {"b": "recurring", "c": "new"}


# ─── link counts ─────────────────────────────────────────────────────────────
def test_new_links_is_na_without_a_baseline():
    counts = diff_link_counts(None, ["a", "b"])
    assert counts == {"has_baseline": False, "new_links": None, "removed_links": None}


def test_new_and_removed_link_counts():
    counts = diff_link_counts(["a", "b"], ["b", "c", "d"])
    assert counts["new_links"] == 2 and counts["removed_links"] == 1


# ─── age ─────────────────────────────────────────────────────────────────────
def test_issue_age_days():
    assert issue_age_days("2026-07-01T00:00:00+00:00", NOW) == 12


def test_issue_age_handles_z_suffix_and_missing_values():
    assert issue_age_days("2026-07-01T00:00:00Z", NOW) == 12
    assert issue_age_days("", NOW) == 0
    assert issue_age_days("not-a-date", NOW) == 0


def test_age_phrase():
    assert age_phrase(_finding("a", first_seen="2026-07-01T00:00:00+00:00"), NOW) == \
        "Broken for 12 days"
    assert age_phrase(_finding("a", first_seen=NOW), NOW) == "Broken since today"
    assert age_phrase(_finding("a", first_seen="2026-07-12T00:00:00+00:00"), NOW) == \
        "Broken for 1 day"
    assert age_phrase(_finding("a", bucket="dead_cta", first_seen=NOW), NOW) == \
        "Open since today"
