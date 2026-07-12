"""Vigilance report compute engine — the numbers must trace to input data."""
from datetime import datetime, timezone, timedelta

from vigilance_report import compute_report


JUN_START = datetime(2026, 6, 1, tzinfo=timezone.utc)
JUN_END = datetime(2026, 6, 30, 23, 59, tzinfo=timezone.utc)


def _scan(day, score, total=80, broken=0, dead=0):
    return {"scanned_at": datetime(2026, 6, day, 12, tzinfo=timezone.utc).isoformat(),
            "health_score": score, "total_links": total, "broken_count": broken, "dead_cta_count": dead}


def test_zero_issue_month_is_vigilance_led_not_empty():
    scans = [_scan(2, 100), _scan(15, 100), _scan(28, 100)]
    r = compute_report(scans, [], JUN_START, JUN_END, forms_audited=3, integrations_watched=12)
    assert r["all_clear"] is True
    assert "stayed healthy" in r["verdict"] and "June 2026" in r["verdict"]
    assert r["vigilance"]["checks_run"] == 3
    assert r["vigilance"]["links_verified"] == 80
    assert r["vigilance"]["forms_audited"] == 3 and r["vigilance"]["integrations_watched"] == 12
    assert r["incidents"] == []


def test_period_windowing_excludes_out_of_range():
    scans = [
        {"scanned_at": datetime(2026, 5, 20, tzinfo=timezone.utc).isoformat(), "health_score": 50, "total_links": 40},  # before
        _scan(10, 90), _scan(20, 95),
        {"scanned_at": datetime(2026, 7, 2, tzinfo=timezone.utc).isoformat(), "health_score": 10, "total_links": 5},   # after
    ]
    r = compute_report(scans, [], JUN_START, JUN_END)
    assert r["vigilance"]["checks_run"] == 2
    assert r["score"] == 95 and r["score_delta"] == 5  # 95 - 90
    assert len(r["trend"]) == 2


def test_caught_and_fixed_builds_timeline_and_verdict():
    scans = [_scan(1, 88, broken=1), _scan(28, 100)]
    findings = [{
        "first_seen_at": datetime(2026, 6, 3, 9, tzinfo=timezone.utc).isoformat(),
        "resolved_at": datetime(2026, 6, 4, 9, tzinfo=timezone.utc).isoformat(),
        "status": "verified_fixed", "bucket": "broken",
        "reason": "Broken booking button", "zone": "CTA", "url": "https://x.com/book",
    }]
    r = compute_report(scans, findings, JUN_START, JUN_END)
    assert r["all_clear"] is False
    assert r["caught_count"] == 1 and r["fixed_count"] == 1
    inc = r["incidents"][0]
    assert inc["verified"] is True and inc["hours_to_fix"] == 24
    assert "within 48 hours" in r["verdict"]


def test_roi_line_only_with_economics():
    findings = [{"first_seen_at": datetime(2026, 6, 3, tzinfo=timezone.utc).isoformat(),
                 "resolved_at": datetime(2026, 6, 3, 2, tzinfo=timezone.utc).isoformat(),
                 "status": "resolved", "bucket": "broken", "reason": "x"}]
    # no economics -> no roi line
    r0 = compute_report([_scan(3, 90)], findings, JUN_START, JUN_END)
    assert "roi_line" not in r0["incidents"][0]
    # with economics -> roi line present
    r1 = compute_report([_scan(3, 90)], findings, JUN_START, JUN_END,
                        economics={"plan_monthly_usd": 100, "value_per_incident_usd": 400})
    assert "4.0× your monthly plan" in r1["incidents"][0]["roi_line"]


def test_streak_counts_from_last_new_issue():
    # last new issue on Jun 20; period end Jun 30 -> ~10 days clean
    findings = [{"first_seen_at": datetime(2026, 6, 20, tzinfo=timezone.utc).isoformat(),
                 "resolved_at": datetime(2026, 6, 21, tzinfo=timezone.utc).isoformat(),
                 "status": "resolved", "bucket": "broken", "reason": "x"}]
    r = compute_report([_scan(20, 90), _scan(30, 100)], findings, JUN_START, JUN_END)
    assert r["streak_days"] == 10
