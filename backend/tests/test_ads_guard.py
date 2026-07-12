"""Ads waste-guard summary — all-clear, breach promotion, honest spend math."""
from datetime import datetime, timezone, timedelta

from ads_guard import summarize_guard

NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)


def _d(campaign, url, status, cost=None, breach_since=None, ad_group=""):
    return {"id": url, "campaign": campaign, "ad_group": ad_group, "final_url": url,
            "status": status, "cost_per_day": cost, "breach_since": breach_since,
            "last_checked_at": NOW.isoformat(), "response_ms": 120}


def test_all_clear_when_nothing_broken():
    dests = [_d("Brand", "https://a/1", "ok"), _d("Brand", "https://a/2", "ok"),
             _d("Leadgen", "https://a/3", "unverifiable")]
    s = summarize_guard(dests, now=NOW)
    assert s["all_clear"] is True          # unverifiable is NOT a breach
    assert s["broken"] == 0 and s["unverifiable"] == 1
    assert s["breaches"] == []
    assert s["last_checked"] is not None


def test_breach_promotes_and_spend_math_with_cost():
    since = (NOW - timedelta(days=3)).isoformat()
    dests = [
        _d("Brand", "https://a/ok", "ok", cost=10),
        _d("Leadgen", "https://a/dead", "broken", cost=20, breach_since=since),
    ]
    s = summarize_guard(dests, now=NOW)
    assert s["all_clear"] is False
    assert len(s["breaches"]) == 1
    assert s["spend"]["daily_at_risk"] == 20.0            # only the broken one
    assert s["spend"]["since_detected"] == 60.0           # 20/day * 3 days
    # breached campaign floats to the top
    assert s["campaigns"][0]["name"] == "Leadgen"


def test_no_cost_means_no_spend_numbers_even_on_breach():
    dests = [_d("Brand", "https://a/dead", "broken")]
    s = summarize_guard(dests, now=NOW)
    assert s["has_cost"] is False
    assert s["spend"]["daily_at_risk"] is None
    assert s["spend"]["since_detected"] is None
    assert len(s["breaches"]) == 1


def test_empty_is_not_all_clear():
    s = summarize_guard([], now=NOW)
    assert s["empty"] is True
    assert s["all_clear"] is False
    assert s["total"] == 0
