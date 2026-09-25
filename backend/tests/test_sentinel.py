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


# ─── the uptime job alerts on the TRANSITION, not on the state ───────────────
# The 5-minute cadence makes this the one place where alerting on state instead
# of on change is not a style point: a site that stays down for eight hours
# produced ~100 identical Slack messages. Every other alert in the product is
# change-only (ladder_crossing, indexability, monitoring's diff) — this closes
# the last gap, and this test is what keeps it closed.
class _FakeIncidents:
    """Mirrors the real database helpers' contract: open_incident returns True
    only when it actually opened a row (it refuses to stack), close_incident
    returns True only when it actually closed one."""

    def __init__(self):
        self.open = False
        self.pings = []          # newest-first, like recent_pings

    async def add_uptime_ping(self, _site_id, up):
        self.pings.insert(0, bool(up))

    async def recent_pings(self, _site_id, limit=3):
        return self.pings[:limit]

    async def open_incident(self, _site_id):
        if self.open:
            return False
        self.open = True
        return True

    async def close_incident(self, _site_id):
        if not self.open:
            return False
        self.open = False
        return True


def _run_uptime_ticks(monkeypatch, up_sequence):
    """Drive run_uptime_for_site once per entry in up_sequence; return the
    Slack lines it would have sent."""
    import asyncio

    import database
    import sentinel

    fake = _FakeIncidents()
    monkeypatch.setattr(database, "add_uptime_ping", fake.add_uptime_ping)
    monkeypatch.setattr(database, "recent_pings", fake.recent_pings)
    monkeypatch.setattr(database, "open_incident", fake.open_incident)
    monkeypatch.setattr(database, "close_incident", fake.close_incident)

    sent = []

    async def _notify(text):
        sent.append(text)

    site = {"id": "site-1", "url": "https://dev.acme.test"}
    for up in up_sequence:
        monkeypatch.setattr(sentinel, "ping", lambda *a, **k: _async_value(up))
        asyncio.run(sentinel.run_uptime_for_site(site, notify=_notify))
    return sent


def _async_value(value):
    async def _coro():
        return value
    return _coro()


def test_a_sustained_outage_alerts_once_not_once_per_check(monkeypatch):
    # 10 consecutive failed checks = 50 minutes down, one outage.
    sent = _run_uptime_ticks(monkeypatch, [False] * 10)
    downs = [s for s in sent if "Site down" in s]
    assert len(downs) == 1, f"expected one down alert for one outage, got {len(downs)}"
    assert "dev.acme.test" in downs[0]


def test_recovery_alerts_once_and_a_second_outage_alerts_again(monkeypatch):
    # down (2 ticks to cross the threshold) → stays down → recovers → down again
    sent = _run_uptime_ticks(
        monkeypatch, [False, False, False, True, True, False, False])
    assert [("down" if "Site down" in s else "up") for s in sent] == ["down", "up", "down"], sent


def test_a_single_blip_never_alerts(monkeypatch):
    # one failure between successes is not an outage — downtime_state needs two
    assert _run_uptime_ticks(monkeypatch, [True, False, True]) == []


# ─── the alerting sweeps respect the monitoring toggle ───────────────────────
# all_sites_min() is unfiltered by design (the fragility/perf recompute jobs
# want every site, and they only write caches). The SENTINEL sweeps alert, and
# they ran on that same unfiltered list — so switching monitoring off did
# nothing for them and an unmonitored dev site still paged every 5 minutes.
def test_the_uptime_sweep_only_visits_monitored_sites(monkeypatch):
    import asyncio

    import database
    import sentinel

    async def _monitored():
        return [{"id": "on", "url": "https://watched.acme.test"}]

    monkeypatch.setattr(database, "monitored_sites_min", _monitored)

    visited = []

    async def _fake_site(site, notify=None, client=None):
        visited.append(site["id"])
        return True

    monkeypatch.setattr(sentinel, "run_uptime_for_site", _fake_site)
    asyncio.run(sentinel.run_uptime_all(notify=None))
    assert visited == ["on"], "the 5-minute sweep must skip sites with monitoring off"


def test_the_daily_sentinel_sweep_only_visits_monitored_sites(monkeypatch):
    import asyncio

    import database
    import sentinel

    async def _monitored():
        return [{"id": "on", "url": "https://watched.acme.test"}]

    monkeypatch.setattr(database, "monitored_sites_min", _monitored)

    visited = []

    async def _fake_site(site, notify=None, client=None):
        visited.append(site["id"])

    monkeypatch.setattr(sentinel, "run_sentinel_for_site", _fake_site)
    asyncio.run(sentinel.run_sentinel_all(notify=None))
    assert visited == ["on"]


def test_an_alerting_sweep_never_reaches_for_the_unfiltered_site_list():
    """Structural guard. Reverting either sweep to all_sites_min silently
    restores the spam, and no behavioural test would notice if the fixture were
    updated alongside it — so pin the source."""
    import inspect

    import sentinel

    for fn in (sentinel.run_uptime_all, sentinel.run_sentinel_all):
        src = inspect.getsource(fn)
        assert "monitored_sites_min" in src, f"{fn.__name__} must use monitored_sites_min"
        assert "all_sites_min" not in src, (
            f"{fn.__name__} alerts, so it must not sweep the unfiltered site list"
        )
