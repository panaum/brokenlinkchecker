"""
Issue identity and lifecycle reconciliation.

If the fingerprint is unstable the whole primitive collapses: issues look new
every scan, ages reset, nothing is ever "fixed". If reconciliation is wrong,
the verification banner lies to the client. Both are covered here.
"""
import pytest

from issues import (
    build_issues_from_scan,
    issue_fingerprint,
    map_region,
    map_severity,
    map_issue_type,
    reconcile_issues,
    summarize_issue_diff,
)
from models import IssueRecord, IssueOccurrence


PAGE = "https://acme.test/pricing"
TARGET = "https://acme.test/gone"


def _fp(target=TARGET, page=PAGE):
    return issue_fingerprint(target, page)


def _issue(target=TARGET, page=PAGE, status="open", first_seen="2026-07-10T00:00:00+00:00",
           itype="broken", region="nav"):
    return IssueRecord(
        fingerprint=issue_fingerprint(target, page),
        status=status,
        issue_type=itype,
        target_url=target,
        source_page_url=page,
        region=region,
        occurrences=[IssueOccurrence(source_page_url=page, region=region, severity="high")],
        occurrence_count=1,
        first_seen_at=first_seen,
        last_seen_at=first_seen,
    )


def _result(url=TARGET, bucket="broken", zones=None, category="Navigation",
            anchor="Book now", priority="critical", source_element="a.book"):
    return {
        "url": url,
        "bucket": bucket,
        "zones": zones if zones is not None else ["Navigation"],
        "category": category,
        "anchor_text": anchor,
        "priority": priority,
        "source_element": source_element,
    }


# ─── fingerprint: normalization edge cases ───────────────────────────────────
@pytest.mark.parametrize("a,b", [
    # trailing slash on the target
    ("https://acme.test/gone/", "https://acme.test/gone"),
    # trailing slash on the source page
    (PAGE + "/", PAGE),
    # utm / click ids on the target never change identity
    ("https://acme.test/gone?utm_source=x", "https://acme.test/gone"),
    ("https://acme.test/gone?fbclid=1&gclid=2", "https://acme.test/gone"),
    # uppercase host and scheme
    ("HTTPS://ACME.TEST/gone", "https://acme.test/gone"),
    # default ports
    ("https://acme.test:443/gone", "https://acme.test/gone"),
    # query order is not identity
    ("https://acme.test/gone?b=2&a=1", "https://acme.test/gone?a=1&b=2"),
])
def test_target_normalization_is_stable(a, b):
    assert issue_fingerprint(a, PAGE) == issue_fingerprint(b, PAGE)


def test_source_page_utm_and_case_do_not_change_identity():
    assert issue_fingerprint(TARGET, "HTTPS://ACME.TEST/pricing?utm_medium=cpc") == _fp()


def test_source_page_fragment_is_dropped():
    # /pricing and /pricing#top are the same page.
    assert issue_fingerprint(TARGET, PAGE + "#top") == _fp()


def test_target_fragment_is_identity():
    # A broken #team and a broken #pricing are two different issues.
    team = issue_fingerprint("https://acme.test/p#team", PAGE)
    pricing = issue_fingerprint("https://acme.test/p#pricing", PAGE)
    assert team != pricing


def test_different_target_or_page_are_different_issues():
    assert _fp("https://acme.test/other") != _fp()
    assert issue_fingerprint(TARGET, "https://acme.test/home") != _fp()


def test_region_is_not_part_of_identity():
    # The documented deviation: one target across nav/hero/footer is ONE issue.
    nav = build_issues_from_scan(PAGE, [_result(zones=["Navigation"])])
    foot = build_issues_from_scan(PAGE, [_result(zones=["Footer"])])
    assert nav[0].fingerprint == foot[0].fingerprint


# ─── mapping helpers ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("zone,region", [
    ("Navigation", "nav"), ("Primary menu", "nav"),
    ("Header", "hero"), ("Hero CTA", "hero"), ("Sticky banner", "hero"),
    ("Body text", "body"), ("", "body"), ("Something else", "body"),
    ("Sidebar", "sidebar"), ("Footer", "footer"),
])
def test_map_region(zone, region):
    assert map_region(zone) == region


@pytest.mark.parametrize("prio,sev", [
    ("critical", "high"), ("high", "high"), ("medium", "med"),
    ("low", "low"), (None, "low"), ("weird", "low"),
])
def test_map_severity(prio, sev):
    assert map_severity(prio) == sev


def test_map_issue_type_falls_back_to_unverifiable():
    assert map_issue_type("broken") == "broken"
    assert map_issue_type("dead_cta") == "dead_cta"
    assert map_issue_type("mystery") == "unverifiable"


# ─── build_issues_from_scan ──────────────────────────────────────────────────
def test_working_links_are_not_issues():
    assert build_issues_from_scan(PAGE, [_result(bucket="ok")]) == []


def test_multi_zone_target_is_one_issue_many_occurrences():
    issues = build_issues_from_scan(PAGE, [_result(zones=["Navigation", "Hero", "Footer"])])
    assert len(issues) == 1
    assert issues[0].occurrence_count == 3
    assert {o.region for o in issues[0].occurrences} == {"nav", "hero", "footer"}
    # Primary region is the highest-severity occurrence's region.
    assert issues[0].region in {"nav", "hero", "footer"}


def test_duplicate_results_merge_and_dedupe_occurrences():
    r = _result(zones=["Navigation"])
    issues = build_issues_from_scan(PAGE, [r, dict(r)])
    assert len(issues) == 1
    assert issues[0].occurrence_count == 1


# ─── reconciliation: the four cases ──────────────────────────────────────────
NOW = "2026-07-22T00:00:00+00:00"


def test_first_scan_has_no_baseline_but_still_inserts_issues():
    # has_baseline False changes the banner copy ("first scan"), but the issues
    # must still be persisted — so they land in `new`, and nothing is `fixed`.
    current = build_issues_from_scan(PAGE, [_result()])
    diff = reconcile_issues(None, current, now=NOW)
    assert diff.has_baseline is False
    assert len(diff.new) == 1
    assert diff.still_open == [] and diff.fixed == []
    assert "First scan" in summarize_issue_diff(diff)


def test_new_issue():
    current = build_issues_from_scan(PAGE, [_result()])
    diff = reconcile_issues([], current, now=NOW)
    assert diff.has_baseline is True
    assert len(diff.new) == 1
    assert diff.new[0].first_seen_at == NOW


def test_still_open_carries_original_age():
    prior = _issue(first_seen="2026-07-01T00:00:00+00:00")
    current = build_issues_from_scan(PAGE, [_result()])
    diff = reconcile_issues([prior], current, now=NOW)
    assert len(diff.still_open) == 1
    assert diff.still_open[0].first_seen_at == "2026-07-01T00:00:00+00:00"
    assert diff.still_open[0].last_seen_at == NOW
    assert diff.new == []


def test_fixed_when_absent():
    prior = _issue()
    diff = reconcile_issues([prior], [], now=NOW)  # scan found nothing
    assert len(diff.fixed) == 1
    assert diff.fixed[0].status == "fixed"
    assert diff.fixed[0].fixed_at == NOW


def test_regressed_fixed_issue_reopens_and_keeps_age():
    prior = _issue(status="fixed", first_seen="2026-07-01T00:00:00+00:00")
    current = build_issues_from_scan(PAGE, [_result()])
    diff = reconcile_issues([prior], current, now=NOW)
    assert len(diff.still_open) == 1
    assert diff.still_open[0].status == "open"
    assert diff.still_open[0].first_seen_at == "2026-07-01T00:00:00+00:00"


# ─── ignored persistence ─────────────────────────────────────────────────────
def test_ignored_issue_present_again_stays_ignored():
    prior = _issue(status="ignored")
    current = build_issues_from_scan(PAGE, [_result()])
    diff = reconcile_issues([prior], current, now=NOW)
    assert len(diff.ignored_still_present) == 1
    assert diff.ignored_still_present[0].status == "ignored"
    assert diff.ignored_still_present[0].last_seen_at == NOW
    # Never resurfaces as open/new.
    assert diff.new == [] and diff.still_open == []


def test_ignored_issue_absent_is_left_untouched():
    prior = _issue(status="ignored")
    diff = reconcile_issues([prior], [], now=NOW)
    # Not fixed, not reported anywhere — ignore means ignore.
    assert diff.fixed == []
    assert diff.ignored_still_present == []
    assert diff.new == [] and diff.still_open == []


def test_summary_line():
    prior_open = _issue(target="https://acme.test/a")
    prior_fixed_target = _issue(target="https://acme.test/b")
    current = build_issues_from_scan(PAGE, [_result(url="https://acme.test/a"),
                                            _result(url="https://acme.test/c")])
    diff = reconcile_issues([prior_open, prior_fixed_target], current, now=NOW)
    # a still open, c new, b fixed
    assert "1 new" in summarize_issue_diff(diff)
    assert "1 fixed" in summarize_issue_diff(diff)
