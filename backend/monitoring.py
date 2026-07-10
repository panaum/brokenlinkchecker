"""
Continuous monitoring — scheduled scans, alert only on change.

This module is deliberately thin. It owns *when* to scan and *whether* to
alert; it owns none of the scanning. The scan, the diff and the snapshot are
the exact same code an interactive scan runs (main.run_scan_once, which drains
main.scan_events). Forking that pipeline would mean two definitions of "a scan"
drifting apart, and the monitor quietly reporting something the dashboard never
would.

Everything it does need — the scan runner, the notifier, the single-link
recheck, the snapshot readers — is injected. So the alerting rules below are
tested without a database, a browser or a network, and the rules are what break
if someone loosens them.

Three disciplines, stated once:

  SILENT BY DEFAULT   nothing changed  -> no alert, ever.
  NEVER ALERT ON DOUBT  a finding in `unverifiable` — bot-blocked, timed out —
                        does not wake anyone at 3am. Only provable broken /
                        dead_cta transitions do.
  NEVER ALERT ON A BLIP a new break is re-checked once before it alerts. A link
                        that passes the recheck was a transient failure and is
                        dropped.
"""
import asyncio
from datetime import datetime, timezone


# ─── cadence ─────────────────────────────────────────────────────────────────
# Daily by default. Hourly is 24x the cost for no real benefit on a link
# monitor: a link that broke an hour ago is not materially worse caught at the
# daily scan, and a client does not want 24 "still fine" checks billed.
_DAY = 24 * 60 * 60
CADENCE_SECONDS = {
    "hourly": 60 * 60,
    "daily": _DAY,
    "weekly": 7 * _DAY,
}
DEFAULT_CADENCE = "daily"

# The add-site form historically stored "Every Hour" / "Daily" / "Weekly", while
# the cadence table is keyed on "hourly" / "daily" / "weekly". Without this map,
# "Every Hour" fell through to the daily default — a site set to hourly was
# silently monitored once a day. Normalise every known spelling to a canonical
# key so old rows and new ones agree.
_CADENCE_ALIASES = {
    "every hour": "hourly", "hourly": "hourly", "hour": "hourly",
    "every day": "daily", "daily": "daily", "day": "daily",
    "every week": "weekly", "weekly": "weekly", "week": "weekly",
}

# Provable. A finding in any other bucket (unverifiable) never alerts.
_ALERTABLE_BREAK_BUCKETS = frozenset({"broken", "dead_cta"})


def normalize_cadence(freq) -> str:
    """Canonical cadence key for any known spelling of a freq. Default daily."""
    return _CADENCE_ALIASES.get((freq or "").strip().lower(), DEFAULT_CADENCE)


def cadence_seconds(freq) -> int:
    """Interval for a site's freq. Unknown or missing -> daily."""
    return CADENCE_SECONDS[normalize_cadence(freq)]


# ─── time ────────────────────────────────────────────────────────────────────
def _parse_iso(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _now(now=None) -> datetime:
    return now or datetime.now(timezone.utc)


# ─── duplicate-fire guard ────────────────────────────────────────────────────
def already_scanned_within_window(last_snapshot_at, freq, now=None,
                                  tolerance: float = 0.5) -> bool:
    """True if a scan already ran recently enough to skip this one.

    Makes a scheduled scan idempotent: safe if Railway ever runs two instances,
    and safe across a restart that re-fires a job. `tolerance` is a fraction of
    the cadence — at 0.5, a daily site is skipped only if the last scan was
    under 12 hours ago, so ordinary jitter never suppresses a due scan.
    """
    last = _parse_iso(last_snapshot_at)
    if last is None:
        return False                      # never scanned: it is due
    elapsed = (_now(now) - last).total_seconds()
    return elapsed < cadence_seconds(freq) * tolerance


# ─── change-only alerting ────────────────────────────────────────────────────
def alertable_from_diff(diff) -> dict:
    """The changes worth an alert, filtered to what we can prove.

    NEW breaks: only `broken`/`dead_cta`. A newly `unverifiable` link is not a
    break we can stand behind. FIXED: anything that was a finding and is now
    resolved — a client wants to hear "the thing I flagged is gone".
    """
    new = getattr(diff, "new", None) or []
    fixed = getattr(diff, "fixed", None) or []
    breaks = [f for f in new if getattr(f, "bucket", None) in _ALERTABLE_BREAK_BUCKETS]
    return {"breaks": breaks, "fixed": list(fixed)}


def _finding_link(finding):
    return getattr(finding, "url", None) or (
        finding.get("url") if isinstance(finding, dict) else None)


async def surviving_breaks(breaks, recheck_link) -> list:
    """Flap protection: re-check each new break once, keep only those still bad.

    `recheck_link(url)` returns a bucket string (or an object/dict with one) for
    a fresh check of that single link. A break whose recheck comes back healthy
    or merely unverifiable was a blip and is dropped — a transient 3am timeout
    must never reach a client.
    """
    survivors = []
    for finding in breaks:
        url = _finding_link(finding)
        if not url:
            survivors.append(finding)     # nothing to recheck against; trust the scan
            continue
        try:
            verdict = await recheck_link(url)
        except Exception:
            # Could not recheck. We already saw it break once; do not upgrade a
            # failure to a pass on our own error, but do not invent one either.
            survivors.append(finding)
            continue
        bucket = verdict if isinstance(verdict, str) else (
            getattr(verdict, "bucket", None)
            or (verdict.get("bucket") if isinstance(verdict, dict) else None))
        if bucket in _ALERTABLE_BREAK_BUCKETS:
            survivors.append(finding)
    return survivors


# ─── the scheduled scan ──────────────────────────────────────────────────────
async def run_monitored_scan(site, *, run_scan, get_last_snapshot,
                             recheck_link, notify, now=None) -> dict:
    """Scan one site on schedule; alert only on a proven change.

    All I/O is injected:
      run_scan(url, email)        -> ScanOutcome   (main.run_scan_once)
      get_last_snapshot(site_id)  -> snapshot dict | None
      recheck_link(url)           -> bucket        (a single fresh check)
      notify(site, outcome, alert)                 (the existing Slack sender)

    Returns a small record of what it decided, for the caller to log.
    """
    site_id = site.get("id")
    url = site.get("url")
    email = site.get("user_email") or "monitor"
    freq = site.get("freq")

    # 1. Duplicate-fire guard, before doing any work.
    try:
        last = await get_last_snapshot(site_id) if site_id else None
    except Exception:
        last = None
    last_at = (last or {}).get("created_at") if isinstance(last, dict) else None
    if already_scanned_within_window(last_at, freq, now):
        return {"site_id": site_id, "status": "skipped_too_soon", "alerted": False}

    # 2. The same pipeline an interactive scan runs. It writes the snapshot and
    #    computes the diff itself — we do not reimplement any of that.
    outcome = await run_scan(url, email)

    # 3. What changed, filtered to what we can prove.
    alert = alertable_from_diff(outcome.diff)

    # 4. Flap protection on the new breaks only. Fixed items need no recheck.
    alert["breaks"] = await surviving_breaks(alert["breaks"], recheck_link)

    # 5. Silent by default. No proven break and nothing fixed -> say nothing.
    if not alert["breaks"] and not alert["fixed"]:
        return {"site_id": site_id, "status": "scanned_no_change", "alerted": False}

    await notify(site, outcome, alert)
    return {
        "site_id": site_id, "status": "scanned_alerted", "alerted": True,
        "breaks": len(alert["breaks"]), "fixed": len(alert["fixed"]),
    }


# ─── weekly per-site digest ──────────────────────────────────────────────────
def weekly_digest(snapshots, now=None) -> dict:
    """"Checked N times, caught X, resolved Y" from snapshot history.

    Snapshots are the ones already stored — newest-first list of
    {created_at, totals_json}. No new storage: the uptime record is a read.
    """
    cutoff = _now(now).timestamp() - 7 * _DAY
    checks = caught = resolved = 0
    health_samples = []
    for snap in snapshots or []:
        at = _parse_iso(snap.get("created_at"))
        if at is None or at.timestamp() < cutoff:
            continue
        totals = snap.get("totals_json") or {}
        checks += 1
        caught += int(totals.get("new") or 0)
        resolved += int(totals.get("fixed") or 0)
        if totals.get("health_score") is not None:
            health_samples.append(int(totals["health_score"]))
    return {
        "window_days": 7,
        "checks": checks,
        "issues_caught": caught,
        "issues_resolved": resolved,
        "current_health": health_samples[0] if health_samples else None,
        "lowest_health": min(health_samples) if health_samples else None,
    }


# ─── status / uptime record (the sellable artifact) ──────────────────────────
def monitoring_status(snapshots, now=None) -> dict:
    """Last checked, current health, consecutive-healthy streak, recent events.

    "Healthy 14 days" is the line a client pays for. A snapshot counts as
    healthy when it recorded zero findings; the streak is how long that has held
    unbroken from the most recent scan backward.
    """
    snaps = sorted(
        [s for s in (snapshots or []) if _parse_iso(s.get("created_at"))],
        key=lambda s: _parse_iso(s["created_at"]), reverse=True)
    if not snaps:
        return {"monitored": True, "last_checked": None, "current_health": None,
                "healthy_streak_days": None, "recent_events": []}

    def findings_of(snap):
        return int((snap.get("totals_json") or {}).get("findings") or 0)

    latest = snaps[0]
    latest_totals = latest.get("totals_json") or {}

    # Consecutive-healthy duration: walk back while each scan had zero findings.
    streak_start = None
    for snap in snaps:
        if findings_of(snap) == 0:
            streak_start = _parse_iso(snap["created_at"])
        else:
            break
    streak_days = None
    if streak_start is not None:
        streak_days = max(0, int((_now(now) - streak_start).total_seconds() // _DAY))

    # Recent change events: scans where something new broke or was fixed.
    events = []
    for snap in snaps[:20]:
        totals = snap.get("totals_json") or {}
        new, fixed = int(totals.get("new") or 0), int(totals.get("fixed") or 0)
        if new or fixed:
            events.append({
                "at": snap.get("created_at"),
                "new": new, "fixed": fixed,
                "health_score": totals.get("health_score"),
            })

    return {
        "monitored": True,
        "last_checked": latest.get("created_at"),
        "current_health": latest_totals.get("health_score"),
        "open_findings": findings_of(latest),
        "healthy_streak_days": streak_days,
        "recent_events": events,
    }


# ─── the scheduler ───────────────────────────────────────────────────────────
class MonitorScheduler:
    """AsyncIOScheduler wrapper: one interval job per monitored site.

    In-process inside the always-on FastAPI service. No separate worker, no
    pg_cron: the backend already runs 24/7 with no function timeout, which is
    what a multi-page scan needs. `run_site` is injected so the scheduler holds
    no scan logic and stays trivially testable.
    """

    def __init__(self, run_site):
        self._run_site = run_site
        self._scheduler = None

    def _ensure(self):
        if self._scheduler is None:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            self._scheduler = AsyncIOScheduler(timezone="UTC")
        return self._scheduler

    def schedule_site(self, site) -> str:
        """Add or replace the job for one site. Returns the job id."""
        scheduler = self._ensure()
        job_id = f"monitor:{site.get('id')}"
        seconds = cadence_seconds(site.get("freq"))
        # replace_existing only dedupes once the scheduler is running; before
        # start() jobs sit in a pending buffer where a second add_job stacks a
        # duplicate. Remove first so a re-schedule truly replaces, started or not.
        if scheduler.get_job(job_id) is not None:
            scheduler.remove_job(job_id)
        scheduler.add_job(
            self._run_site, "interval", seconds=seconds, args=[site],
            id=job_id, replace_existing=True,
            # A slow scan must never stack on top of itself, and a scan missed
            # over a restart runs once on resume, not once per hour it was down.
            max_instances=1, coalesce=True,
            # A scan missed over a restart still runs, within half a cadence.
            # Floored at 1s: APScheduler rejects a zero grace time.
            misfire_grace_time=max(1, int(seconds * 0.5)),
        )
        return job_id

    def load(self, sites) -> int:
        """Register a job for every monitored site. Does NOT start ticking.

        Separate from start() because AsyncIOScheduler.start() binds the running
        event loop, so it must be called from inside the async lifespan — while
        the jobs themselves can be registered (and asserted on) synchronously.
        """
        count = 0
        for site in sites or []:
            if site.get("monitoring_enabled"):
                self.schedule_site(site)
                count += 1
        return count

    def start(self, sites=None) -> int:
        """Register any given sites, then start the loop. Returns jobs loaded."""
        count = self.load(sites) if sites is not None else len(self.job_ids)
        scheduler = self._ensure()
        if not scheduler.running:
            scheduler.start()
        return count

    def unschedule_site(self, site_id) -> bool:
        """Remove a site's job. Returns whether one was there."""
        if self._scheduler is None:
            return False
        job_id = f"monitor:{site_id}"
        if self._scheduler.get_job(job_id) is None:
            return False
        self._scheduler.remove_job(job_id)
        return True

    def shutdown(self):
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    @property
    def job_ids(self):
        if self._scheduler is None:
            return []
        return [j.id for j in self._scheduler.get_jobs()]
