"""Disaster Sentinel pure logic — the numbers and thresholds that drive alerts."""
from datetime import datetime, timezone, timedelta

from sentinel import (days_until, escalation, ladder_crossing, indexability_verdict,
                      downtime_state, uptime_pct, summarize_sentinel)

NOW = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)


def test_days_until_floors_and_handles_timezone_edges():
    # expires in ~2 hours today → 0 days remaining, not 1
    soon = (NOW + timedelta(hours=2)).isoformat()
    assert days_until(soon, NOW) == 0
    assert days_until((NOW + timedelta(days=14, hours=5)).isoformat(), NOW) == 14
    # a 'Z'-suffixed / naive timestamp still parses
    assert days_until("2026-07-15T12:00:00Z", NOW) == 3
    # unknown expiry (RDAP hid it) → None, never a guess
    assert days_until(None, NOW) is None


def test_escalation_tiers():
    assert escalation(None) == "unknown"
    assert escalation(2) == "critical"
    assert escalation(3) == "critical"
    assert escalation(10) == "warn"
    assert escalation(14) == "warn"
    assert escalation(20) == "notice"
    assert escalation(30) == "notice"
    assert escalation(90) == "ok"


def test_ladder_crossing_is_change_only():
    assert ladder_crossing(40, 29) == 30     # crossed 30 rung
    assert ladder_crossing(29, 20) is None   # still between 30 and 14, no new rung
    assert ladder_crossing(15, 13) == 14     # crossed 14
    assert ladder_crossing(5, 2) == 3        # crossed 3
    assert ladder_crossing(None, 2) == 3     # first-ever check already critical
    assert ladder_crossing(2, 1) is None     # already past 3, no re-alert


def test_indexability_noindex_via_meta_or_header_is_critical():
    v_meta = indexability_verdict(True, True, False, True)
    assert v_meta["overall"] == "critical"
    v_header = indexability_verdict(True, False, True, True)
    assert v_header["overall"] == "critical"
    v_robots = indexability_verdict(False, False, False, True)
    assert v_robots["overall"] == "critical"
    # only a broken sitemap → a lesser notice, not critical (existing pages stay indexed)
    v_sitemap = indexability_verdict(True, False, False, False)
    assert v_sitemap["overall"] == "notice"
    # all good
    assert indexability_verdict(True, False, False, True)["overall"] == "ok"
    # couldn't determine any → unknown, shown honestly
    assert indexability_verdict(None, None, None, None)["overall"] == "unknown"


def test_downtime_needs_two_consecutive_failures():
    assert downtime_state([False, False, True]) is True     # two in a row → outage
    assert downtime_state([False, True, False]) is False    # single blip, not down
    assert downtime_state([True, True]) is False
    assert downtime_state([False]) is False                 # not enough data


def test_uptime_pct():
    assert uptime_pct([True, True, True, False]) == 75.0
    assert uptime_pct([]) is None
    assert uptime_pct([True, None, True]) == 100.0          # None pings ignored


def test_summarize_puts_most_urgent_card_first_and_honest_unavailable():
    status = {
        "ssl_expiry": (NOW + timedelta(days=200)).isoformat(), "ssl_issuer": "Let's Encrypt",
        "domain_expiry": None,   # registry hid it
        "robots_ok": True, "meta_noindex": True, "header_noindex": False, "sitemap_ok": True,
        "last_checked_at": NOW.isoformat(),
    }
    s = summarize_sentinel(status, pings=[True] * 100, now=NOW)
    # noindex → search-visibility card is critical → sorts to first (proximity=prominence)
    assert s["cards"][0]["key"] == "index"
    assert s["worst"] == "critical"
    # domain expiry unavailable, surfaced honestly
    dom = next(c for c in s["cards"] if c["key"] == "domain")
    assert dom["fact"] == "unavailable" and dom["escalation"] == "unknown"
    assert s["uptime_pct"] == 100.0
