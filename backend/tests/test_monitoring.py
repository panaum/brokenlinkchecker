"""
Monitoring: schedule scans, alert only on a proven change.

Every alerting rule here is a promise to a client's phone at 3am. The tests are
the promises: silent when nothing changed, silent on doubt, silent on a blip.
All dependencies are injected, so none of this touches a browser, a database or
the network — what breaks a test is a loosened rule, not a flaky endpoint.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import monitoring as M


NOW = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)


def _iso(dt):
    return dt.isoformat()


# ─── a finding, and a diff, without importing the whole model ────────────────
class _Finding:
    def __init__(self, url, bucket):
        self.url = url
        self.bucket = bucket


class _Diff:
    def __init__(self, new=(), fixed=()):
        self.new = list(new)
        self.fixed = list(fixed)


class _Outcome:
    def __init__(self, diff):
        self.diff = diff
        self.url = "https://acme.test"
        self.health_score = 90


# ─── cadence ─────────────────────────────────────────────────────────────────
def test_default_cadence_is_daily_not_hourly():
    assert M.cadence_seconds(None) == 24 * 60 * 60
    assert M.cadence_seconds("") == 24 * 60 * 60
    assert M.cadence_seconds("nonsense") == 24 * 60 * 60


def test_freq_overrides_the_default():
    assert M.cadence_seconds("hourly") == 3600
    assert M.cadence_seconds("weekly") == 7 * 24 * 60 * 60
    assert M.cadence_seconds("DAILY") == 24 * 60 * 60


# ─── duplicate-fire guard ────────────────────────────────────────────────────
def test_a_never_scanned_site_is_due():
    assert M.already_scanned_within_window(None, "daily", now=NOW) is False


def test_a_scan_an_hour_ago_skips_a_daily_site():
    an_hour_ago = _iso(NOW - timedelta(hours=1))
    assert M.already_scanned_within_window(an_hour_ago, "daily", now=NOW) is True


def test_a_scan_yesterday_does_not_skip_a_daily_site():
    yesterday = _iso(NOW - timedelta(hours=25))
    assert M.already_scanned_within_window(yesterday, "daily", now=NOW) is False


def test_the_guard_scales_with_cadence():
    # An hourly site scanned 10 minutes ago is too soon; a daily one is not.
    ten_min = _iso(NOW - timedelta(minutes=10))
    assert M.already_scanned_within_window(ten_min, "hourly", now=NOW) is True
    assert M.already_scanned_within_window(ten_min, "daily", now=NOW) is True
    forty_min = _iso(NOW - timedelta(minutes=40))
    assert M.already_scanned_within_window(forty_min, "hourly", now=NOW) is False


# ─── change-only alerting ────────────────────────────────────────────────────
def test_no_change_produces_no_alertable_items():
    alert = M.alertable_from_diff(_Diff())
    assert alert["breaks"] == [] and alert["fixed"] == []


def test_a_new_broken_link_is_alertable():
    diff = _Diff(new=[_Finding("https://x/gone", "broken")])
    assert len(M.alertable_from_diff(diff)["breaks"]) == 1


def test_a_new_dead_cta_is_alertable():
    diff = _Diff(new=[_Finding("https://x/cta", "dead_cta")])
    assert len(M.alertable_from_diff(diff)["breaks"]) == 1


def test_a_new_unverifiable_link_is_never_alertable():
    """Bot-blocked or timed out at 3am must not wake anyone."""
    diff = _Diff(new=[_Finding("https://x/blocked", "unverifiable")])
    assert M.alertable_from_diff(diff)["breaks"] == []


def test_a_fixed_finding_is_alertable():
    diff = _Diff(fixed=[_Finding("https://x/was-broken", "broken")])
    assert len(M.alertable_from_diff(diff)["fixed"]) == 1


# ─── flap protection ─────────────────────────────────────────────────────────
def _recheck_returning(mapping):
    async def recheck(url):
        return mapping[url]
    return recheck


def test_a_break_that_survives_recheck_is_kept():
    breaks = [_Finding("https://x/gone", "broken")]
    recheck = _recheck_returning({"https://x/gone": "broken"})
    survivors = asyncio.run(M.surviving_breaks(breaks, recheck))
    assert len(survivors) == 1


def test_a_break_that_recovers_on_recheck_is_dropped():
    breaks = [_Finding("https://x/blip", "broken")]
    recheck = _recheck_returning({"https://x/blip": "ok"})
    assert asyncio.run(M.surviving_breaks(breaks, recheck)) == []


def test_a_break_that_becomes_unverifiable_on_recheck_is_dropped():
    """It broke, then merely could-not-verify. That is not proof; drop it."""
    breaks = [_Finding("https://x/blip", "broken")]
    recheck = _recheck_returning({"https://x/blip": "unverifiable"})
    assert asyncio.run(M.surviving_breaks(breaks, recheck)) == []


def test_a_recheck_that_errors_keeps_the_break():
    """We already saw it fail; our own error must not clear it."""
    async def recheck(url):
        raise RuntimeError("network")
    survivors = asyncio.run(
        M.surviving_breaks([_Finding("https://x/gone", "broken")], recheck))
    assert len(survivors) == 1


# ─── the whole scheduled scan ────────────────────────────────────────────────
def _harness(diff, *, last_snapshot=None, recheck=None):
    """A run_monitored_scan wired to spies. Returns (call, notified)."""
    notified = []

    async def run_scan(url, email):
        return _Outcome(diff)

    async def get_last_snapshot(site_id):
        return last_snapshot

    async def notify(site, outcome, alert):
        notified.append(alert)

    recheck = recheck or _recheck_returning({})
    site = {"id": "s1", "url": "https://acme.test", "freq": "daily",
            "user_email": "c@x.test"}

    async def call():
        return await M.run_monitored_scan(
            site, run_scan=run_scan, get_last_snapshot=get_last_snapshot,
            recheck_link=recheck, notify=notify, now=NOW)

    return call, notified


def test_no_change_scan_sends_no_alert():
    call, notified = _harness(_Diff())
    result = asyncio.run(call())
    assert result["status"] == "scanned_no_change"
    assert result["alerted"] is False
    assert notified == []


def test_a_new_broken_link_alerts_after_passing_recheck():
    diff = _Diff(new=[_Finding("https://x/gone", "broken")])
    call, notified = _harness(diff, recheck=_recheck_returning({"https://x/gone": "broken"}))
    result = asyncio.run(call())
    assert result["status"] == "scanned_alerted" and result["alerted"] is True
    assert len(notified) == 1 and len(notified[0]["breaks"]) == 1


def test_a_new_break_that_fails_recheck_does_not_alert():
    diff = _Diff(new=[_Finding("https://x/blip", "broken")])
    call, notified = _harness(diff, recheck=_recheck_returning({"https://x/blip": "ok"}))
    result = asyncio.run(call())
    assert result["status"] == "scanned_no_change"
    assert notified == []


def test_an_unverifiable_break_never_reaches_recheck_or_alert():
    diff = _Diff(new=[_Finding("https://x/blocked", "unverifiable")])

    async def recheck(url):
        raise AssertionError("unverifiable must be filtered before recheck")

    call, notified = _harness(diff, recheck=recheck)
    result = asyncio.run(call())
    assert result["alerted"] is False and notified == []


def test_a_fixed_finding_alerts_with_no_recheck():
    diff = _Diff(fixed=[_Finding("https://x/back", "broken")])
    call, notified = _harness(diff)
    result = asyncio.run(call())
    assert result["status"] == "scanned_alerted"
    assert len(notified[0]["fixed"]) == 1


def test_a_too_soon_site_is_skipped_without_scanning():
    scanned = []

    async def run_scan(url, email):
        scanned.append(url)
        return _Outcome(_Diff())

    async def get_last_snapshot(site_id):
        return {"created_at": _iso(NOW - timedelta(hours=1))}

    async def notify(site, outcome, alert):
        raise AssertionError("must not alert on a skipped scan")

    site = {"id": "s1", "url": "https://acme.test", "freq": "daily"}
    result = asyncio.run(M.run_monitored_scan(
        site, run_scan=run_scan, get_last_snapshot=get_last_snapshot,
        recheck_link=_recheck_returning({}), notify=notify, now=NOW))
    assert result["status"] == "skipped_too_soon"
    assert scanned == []


# ─── digest ──────────────────────────────────────────────────────────────────
def _snap(days_ago, **totals):
    return {"created_at": _iso(NOW - timedelta(days=days_ago)),
            "totals_json": totals}


def test_weekly_digest_counts_only_the_last_seven_days():
    snaps = [
        _snap(1, new=2, fixed=1, findings=3, health_score=80),
        _snap(3, new=1, fixed=0, findings=4, health_score=78),
        _snap(9, new=5, fixed=5, findings=0, health_score=99),   # outside window
    ]
    d = M.weekly_digest(snaps, now=NOW)
    assert d["checks"] == 2
    assert d["issues_caught"] == 3      # 2 + 1
    assert d["issues_resolved"] == 1    # 1 + 0


def test_weekly_digest_of_a_quiet_week_is_all_zeros():
    d = M.weekly_digest([_snap(1, new=0, fixed=0, findings=0, health_score=100)], now=NOW)
    assert d["checks"] == 1 and d["issues_caught"] == 0 and d["issues_resolved"] == 0


def test_weekly_digest_of_no_history_does_not_crash():
    d = M.weekly_digest([], now=NOW)
    assert d["checks"] == 0 and d["current_health"] is None


# ─── status / uptime record ──────────────────────────────────────────────────
def test_status_reports_a_healthy_streak():
    snaps = [_snap(i, new=0, fixed=0, findings=0, health_score=100) for i in range(0, 14)]
    status = M.monitoring_status(snaps, now=NOW)
    assert status["current_health"] == 100
    assert status["healthy_streak_days"] >= 13


def test_the_streak_breaks_at_the_last_scan_with_findings():
    snaps = [
        _snap(0, findings=0, health_score=100),
        _snap(1, findings=0, health_score=100),
        _snap(2, findings=3, health_score=70),   # streak stops here
        _snap(3, findings=0, health_score=100),
    ]
    status = M.monitoring_status(snaps, now=NOW)
    assert status["healthy_streak_days"] <= 2


def test_status_lists_recent_change_events_only():
    snaps = [
        _snap(0, new=0, fixed=0, findings=0, health_score=100),
        _snap(1, new=2, fixed=0, findings=2, health_score=80),
        _snap(2, new=0, fixed=1, findings=0, health_score=100),
    ]
    events = M.monitoring_status(snaps, now=NOW)["recent_events"]
    assert len(events) == 2                       # the no-change scan is not an event


def test_status_of_a_site_never_scanned():
    status = M.monitoring_status([], now=NOW)
    assert status["last_checked"] is None and status["healthy_streak_days"] is None


# ─── scheduler ───────────────────────────────────────────────────────────────
def test_the_scheduler_schedules_one_job_per_monitored_site():
    ran = []
    sched = M.MonitorScheduler(run_site=lambda site: ran.append(site))
    count = sched.load([
        {"id": "a", "freq": "daily", "monitoring_enabled": True},
        {"id": "b", "freq": "hourly", "monitoring_enabled": True},
        {"id": "c", "freq": "daily", "monitoring_enabled": False},   # off
    ])
    assert count == 2
    assert set(sched.job_ids) == {"monitor:a", "monitor:b"}


def test_a_site_is_scheduled_at_its_own_freq():
    sched = M.MonitorScheduler(run_site=lambda site: None)
    sched.load([{"id": "h", "freq": "hourly", "monitoring_enabled": True}])
    job = next(j for j in sched._scheduler.get_jobs() if j.id == "monitor:h")
    assert int(job.trigger.interval.total_seconds()) == 3600


def test_rescheduling_a_site_replaces_its_job_not_duplicates_it():
    sched = M.MonitorScheduler(run_site=lambda site: None)
    site = {"id": "a", "freq": "daily", "monitoring_enabled": True}
    sched.load([site])
    sched.schedule_site({**site, "freq": "hourly"})
    assert sched.job_ids.count("monitor:a") == 1


def test_a_short_cadence_does_not_produce_a_zero_grace_time():
    """misfire_grace_time=0 is rejected by APScheduler; a 1s job must still add."""
    import monitoring as MM
    orig = MM.cadence_seconds
    MM.cadence_seconds = lambda freq: 1
    sched = MM.MonitorScheduler(run_site=lambda site: None)
    try:
        sched.schedule_site({"id": "z", "freq": "hourly"})
        job = next(j for j in sched._scheduler.get_jobs() if j.id == "monitor:z")
        assert job.misfire_grace_time >= 1
    finally:
        MM.cadence_seconds = orig
