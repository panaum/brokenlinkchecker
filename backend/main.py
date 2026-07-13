import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import json
import time
import base64
import os
from urllib.parse import quote

import httpx

DEFAULT_FRONTEND_URL = "https://brokenlinkchecker-olive.vercel.app"


def _frontend_url() -> str:
    """Where "View Full Report" points. Configurable so a preview deploy or a
    local frontend doesn't send people to production."""
    return os.getenv("FRONTEND_URL", DEFAULT_FRONTEND_URL).rstrip("/")

from fastapi import FastAPI, Query, Depends, Request
from auth import (
    require_site_access, require_scan_access, require_finding_access, require_role,
)
from models import FindingRecord, LinkResult, SiteCreate
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse, JSONResponse

from scraper import scrape_links
from checker import check_all_links
from suggester import process_suggestions
from database import (
    describe_exception,
    diffing_tables_ready,
    get_finding,
    get_site_url,
    last_snapshot_error,
    mark_finding_verified,
    snapshot_write_probe,
    get_findings_for_snapshot,
    get_latest_snapshot,
    get_recent_snapshots,
    get_site_id,
    save_scan,
    save_snapshot,
    site_storage_report,
)
from correlation import enrich_reasons
from form_audit import audit_forms, probe_action_methods
from tracking_audit import audit_tracking
from integration_audit import collect_integrations, unchecked_resource_urls, status_to_health
from database import save_integrations, update_integration_health, get_integrations
from watchdog import (
    inventory_hosts, demote_third_party_failures, aggregate_outages, run_watchdog,
)
from database import (
    get_expected_tracking, set_expected_tracking,
    upsert_host_inventory, get_watchdog_inventory,
    get_recently_alerted, record_host_alert,
    get_form_optin, set_form_optin, list_form_optins,
)
from active_submission import active_testing_enabled
from fix_engine import build_fix_suggestion, choose_builder, render_client_message
from fix_pack import build_fix_pack, build_rows
from fix_verify import verify_finding
from redirect_rules import FORMATS, collapse_rules, redirect_summary, render
from resources import host_breakdown, link_type_breakdown, scheme_breakdown
from diffing import (
    collect_findings,
    diff_findings,
    diff_link_counts,
    diff_status_by_fingerprint,
    fingerprint_result,
    issue_age_days,
    summarize_diff,
    utcnow_iso,
)
from sitemap import discover_site_urls
from database import get_monitored_sites, set_monitoring, get_site
import monitoring
from monitoring import MonitorScheduler, run_monitored_scan, monitoring_status, weekly_digest
from models import RawLink
from checker import check_single
from contextlib import asynccontextmanager


# ─────────────────────────────────────────────────────────────────────────────
# Monitoring wiring. The scheduler holds no scan logic; it calls these adapters,
# each of which is the existing pipeline, not a reimplementation of it.
# ─────────────────────────────────────────────────────────────────────────────
async def _watchdog_slack(text: str, outage: dict = None) -> None:
    """Post one third-party outage alert to Slack. Reuses the same webhook the
    scan notifier uses; a distinct header so it is not mistaken for a scan."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return
    blocks = [
        {"type": "header", "text": {"type": "plain_text",
                                    "text": "🐕 LinkSpy Watchdog — third-party outage"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
    ]
    try:
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json={"blocks": blocks}, timeout=5.0)
    except Exception as e:
        print(f"[Watchdog] Slack failed: {e}")


async def _persist_and_check_integrations(scan_id, page_url: str, integrations: list) -> None:
    """Store this page's integrations, then health-check the few resources the
    scan did not already check — in the background, never blocking the stream.
    Best-effort: a failure here never touches the scan."""
    if not scan_id or not integrations:
        return
    try:
        await save_integrations(scan_id, page_url, integrations)
    except Exception as e:
        print(f"[Integrations] save skipped: {type(e).__name__}: {e}")
        return
    pending = unchecked_resource_urls(integrations)
    if pending:
        asyncio.create_task(_background_integration_health(scan_id, pending))


async def _background_integration_health(scan_id, urls: list) -> None:
    """Lightweight GET per still-unknown resource; persist each verdict as it
    lands. 5s timeout, follow redirects, bot-blocks stay 'unknown' not 'down'."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=5) as client:
        for u in urls:
            health = "unknown"
            try:
                resp = await client.get(u, headers={"User-Agent": "Mozilla/5.0 LinkSpy"})
                health = status_to_health(resp.status_code)
            except (httpx.TimeoutException,):
                health = "unresponsive"
            except Exception:
                health = "unknown"
            try:
                await update_integration_health(scan_id, u, health)
            except Exception:
                pass


async def _run_watchdog_after_scan(site_id, results, page_url: str) -> None:
    """Record this scan's third-party hosts; alert on any cross-site outage.

    Everything here is best-effort and wrapped: a watchdog or DB failure must
    never affect the scan that triggered it.
    """
    try:
        records = inventory_hosts(results, page_url)
        if site_id:
            await upsert_host_inventory(site_id, records)
        # Only bother aggregating when this scan actually saw something down.
        if not any(r.get("down") for r in records):
            return
        await run_watchdog(
            get_inventory=get_watchdog_inventory,
            get_recently_alerted=get_recently_alerted,
            record_alert=lambda host, _ts: record_host_alert(host),
            notify=_watchdog_slack,
            now_ts=time.time(),
        )
    except Exception as e:
        print(f"[Watchdog] skipped (non-critical): {type(e).__name__}: {e}")


async def _expected_tracking(url: str, email: str) -> dict:
    """The site's stored GA4/Meta/GTM ids, or None. Best-effort: a lookup
    failure (no column, no site) never fails a scan — it just skips the
    mismatch check."""
    try:
        return await get_expected_tracking(url, email)
    except Exception:
        return None


async def _recheck_link(url: str) -> str:
    """One fresh check of a single link, for flap protection. Returns a bucket.

    Reuses checker.check_single — the same code path the scan uses per link — so
    a recheck agrees with the scan by construction.
    """
    link = RawLink(url=url, source_element="a", anchor_text="", category="Other",
                   is_external=True, zones=["Other"], link_kind="http")
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        result = await check_single(client, link)
    return getattr(result, "bucket", None) or "unverifiable"


async def _notify_change(site: dict, outcome, alert: dict) -> None:
    """Change-only alert. Reuses the existing Slack sender; the diff summary it
    already builds names what changed."""
    await send_slack_notification(
        site.get("url"), outcome.health_score, outcome.results,
        diff_summary=outcome.diff_payload.get("summary", ""),
    )


async def _run_site(site: dict) -> dict:
    return await run_monitored_scan(
        site, run_scan=run_scan_once, get_last_snapshot=get_latest_snapshot,
        recheck_link=_recheck_link, notify=_notify_change,
    )


_scheduler = MonitorScheduler(run_site=_run_site)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the in-process scheduler inside the always-on Railway service.
    try:
        sites = await get_monitored_sites()
        loaded = _scheduler.start(sites)
        print(f"[Monitor] scheduler started with {loaded} monitored site(s)")
        # Wave 2: daily ads waste-guard verification on the same scheduler.
        try:
            from ads_guard import run_ads_verification
            aps = _scheduler._scheduler
            if aps:
                aps.add_job(run_ads_verification, "interval", hours=24,
                            id="ads_verification", replace_existing=True,
                            kwargs={"notify": _watchdog_slack})
                print("[AdsGuard] daily verification scheduled")
        except Exception as e:
            print(f"[AdsGuard] verification not scheduled: {e}")
        # Wave 3: Disaster Sentinel — daily SSL/domain/indexability + 5-min uptime.
        try:
            from sentinel import run_sentinel_all, run_uptime_all
            aps = _scheduler._scheduler
            if aps:
                aps.add_job(run_sentinel_all, "interval", hours=24, id="sentinel_daily",
                            replace_existing=True, kwargs={"notify": _watchdog_slack})
                aps.add_job(run_uptime_all, "interval", minutes=5, id="sentinel_uptime",
                            replace_existing=True, kwargs={"notify": _watchdog_slack})
                print("[Sentinel] daily checks + 5-min uptime scheduled")
                aps.add_job(_recompute_perf_all, "cron", hour=3, minute=30, id="perf_recompute",
                            replace_existing=True, misfire_grace_time=3600)
        except Exception as e:
            print(f"[Sentinel] not scheduled: {e}")
        # Wave 2 (lead delivery): daily tracer sweep over armed enrollments.
        try:
            from tracer import tracer_enabled
            aps = _scheduler._scheduler
            if aps:
                aps.add_job(_run_tracer_sweep, "cron", hour=6, minute=0, id="tracer_daily",
                            replace_existing=True, misfire_grace_time=3600)
                print(f"[Tracer] daily sweep scheduled (enabled={tracer_enabled()})")
        except Exception as e:
            print(f"[Tracer] not scheduled: {e}")
    except Exception as e:
        # Monitoring failing to start must never take the API down.
        print(f"[Monitor] scheduler did not start: {e}")
    yield
    try:
        _scheduler.shutdown()
    except Exception:
        pass


app = FastAPI(title="Broken Link Checker API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://brokenlinkchecker-olive.vercel.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Screenshot cache ─────────────────────────────────────────────────────────
_preview_cache: dict[str, tuple[str, float]] = {}
_PREVIEW_CACHE_TTL = 600  # 10 minutes


async def send_slack_notification(
    url: str,
    health_score: int,
    results: list,
    diff_summary: str = "",
) -> None:
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return

    total = len(results)
    working = sum(1 for r in results if r.label == "ok")
    broken = [r for r in results if r.label == "broken"]
    dead_cta = [r for r in results if r.label == "dead_cta"]
    redirects = sum(1 for r in results if r.label == "redirect")
    blocked = sum(1 for r in results if r.label == "blocked")

    if health_score >= 90:
        score_emoji = "✅"
    elif health_score >= 70:
        score_emoji = "⚠️"
    else:
        score_emoji = "🔴"

    # Build broken links text
    broken_text = ""
    if broken:
        lines = []
        for r in broken[:5]:
            path = r.url.replace("https://", "").replace("http://", "")
            path = "/" + "/".join(path.split("/")[1:]) if "/" in path else path
            lines.append(f"• `{path[:50]}` — {r.category}")
        if len(broken) > 5:
            lines.append(f"• ...and {len(broken) - 5} more")
        broken_text = "\n".join(lines)

    # Build dead CTAs text
    cta_text = ""
    if dead_cta:
        lines = []
        for r in dead_cta[:3]:
            anchor = r.anchor_text or "[no text]"
            # `zones` names the page regions the link sits in; source_element is
            # just the tag name and says nothing useful on its own.
            zones = getattr(r, "zones", None) or []
            where = ", ".join(zones) or getattr(r, "category", "") or "Unknown location"
            lines.append(f"• \"{anchor[:30]}\" — {where[:40]}")
        if len(dead_cta) > 3:
            lines.append(f"• ...and {len(dead_cta) - 3} more")
        cta_text = "\n".join(lines)

    # Build message blocks
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🔍 LinkSpy Scan Complete"
            }
        },
    ]

    # Every report leads with the diff: "N new · M fixed · K still open".
    if diff_summary:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"*{diff_summary}*"}],
        })

    blocks += [
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Site:*\n{url}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Health Score:*\n{health_score}/100 {score_emoji}"
                }
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Summary:*\n"
                    f"• Total links: {total}\n"
                    f"• ✅ Working: {working}\n"
                    f"• ❌ Broken: {len(broken)}\n"
                    f"• ⚠️ Dead CTAs: {len(dead_cta)}\n"
                    f"• 🔄 Redirects: {redirects}\n"
                    f"• 🔍 Can't verify: {blocked}"
                )
            }
        }
    ]

    if broken_text:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*❌ Broken Links:*\n{broken_text}"
            }
        })

    if cta_text:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*⚠️ Dead CTAs:*\n{cta_text}"
            }
        })

    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "View Full Report →"
                },
                # The scanned URL must be percent-encoded: it carries "://" and
                # may carry its own ?query, which would otherwise terminate ours.
                # Slack rejects a button whose URL it cannot parse.
                "url": f"{_frontend_url()}/?url={quote(url, safe='')}",
                "style": "primary"
            }
        ]
    })

    payload = {"blocks": blocks}

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                webhook_url, 
                json=payload, 
                timeout=5.0
            )
    except Exception as e:
        print(f"[Slack] Failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — baseline diffing
#
# A scan never fails because diffing failed. But it must report *which* of the
# two no-baseline cases it hit: a genuine first scan, or a lookup that failed
# (usually migrations/001 not applied). Reporting both as "first scan" tells a
# user who has scanned a site fifty times that there is nothing to compare
# against, forever, with the real error buried in a server log.
# ─────────────────────────────────────────────────────────────────────────────
def _findings_from_rows(rows: list) -> list:
    out = []
    for row in rows or []:
        try:
            out.append(FindingRecord(**{
                k: row.get(k) for k in FindingRecord.model_fields if k in row
            }))
        except Exception:
            continue   # a malformed row must not poison the diff
    return out


async def _load_baseline(site_id):
    """(previous_findings, previous_link_fingerprints). (None, None) = no baseline."""
    if not site_id:
        return None, None
    snapshot = await get_latest_snapshot(site_id)
    if not snapshot:
        return None, None
    rows = await get_findings_for_snapshot(snapshot["id"])
    totals = snapshot.get("totals_json") or {}
    return _findings_from_rows(rows), totals.get("link_fingerprints")


def _finding_payload(finding, now: str) -> dict:
    data = finding.model_dump()
    data["age_days"] = issue_age_days(finding.first_seen_at, now)
    return data


# Why there is no baseline. "first_scan" is normal; "unavailable" means the
# lookup failed (usually migrations/001 has not been applied), and the UI must
# say so instead of claiming this is the site's first scan.
BASELINE_OK = "ok"
BASELINE_FIRST_SCAN = "first_scan"
BASELINE_UNAVAILABLE = "unavailable"


def _diff_payload(diff, link_counts: dict, now: str,
                  baseline_status: str = BASELINE_FIRST_SCAN) -> dict:
    return {
        "has_baseline": diff.has_baseline,
        "baseline_status": BASELINE_OK if diff.has_baseline else baseline_status,
        # The lead line for every report and email.
        "summary": summarize_diff(diff),
        "new": len(diff.new),
        "fixed": len(diff.fixed),
        "recurring": len(diff.recurring),
        # n/a on the first scan of a site.
        "new_links": link_counts.get("new_links"),
        "removed_links": link_counts.get("removed_links"),
        # Fixed findings are gone from `results`, so carry them here.
        "fixed_findings": [_finding_payload(f, now) for f in diff.fixed],
    }


def _annotate_results(results, page_url_of, diff, now: str) -> None:
    """Stamp fingerprint / diff_status / age_days onto each flagged result."""
    status_map = diff_status_by_fingerprint(diff)
    first_seen = {f.fingerprint: f.first_seen_at for f in diff.new + diff.recurring}

    for r in results:
        bucket = r.get("bucket") if isinstance(r, dict) else getattr(r, "bucket", None)
        page = page_url_of(r)
        fp = fingerprint_result(page, r)

        if isinstance(r, dict):
            r["fingerprint"] = fp
        else:
            r.fingerprint = fp

        if bucket in (None, "ok"):
            continue   # a working link is not a finding

        status = status_map.get(fp)
        seen_at = first_seen.get(fp)
        age = issue_age_days(seen_at, now) if seen_at else None
        if isinstance(r, dict):
            r["diff_status"] = status
            r["first_seen_at"] = seen_at
            r["age_days"] = age
        else:
            r.diff_status = status
            r.first_seen_at = seen_at
            r.age_days = age


async def _run_diff(site_url: str, user_email: str, results, page_url_of) -> tuple:
    """Diff this scan against the site's previous snapshot and annotate results.

    Returns (diff, link_counts, now, site_id, current_findings, current_fps,
             baseline_status).
    """
    now = utcnow_iso()
    baseline_status = BASELINE_FIRST_SCAN
    try:
        site_id = await get_site_id(site_url, user_email)
        previous_findings, previous_fps = await _load_baseline(site_id)
    except Exception as e:
        # A failed lookup is NOT a first scan. Say which one it was, or the UI
        # will report "no previous scan" on a site scanned a hundred times.
        print(f"[Diff] baseline lookup failed: {type(e).__name__}: {e}")
        baseline_status = BASELINE_UNAVAILABLE
        site_id, previous_findings, previous_fps = None, None, None

    # Dedupe across the whole scan, not per result: a site scan can surface the
    # same destination from several pages.
    current_findings, current_fps = [], []
    seen_findings, seen_links = set(), set()

    for r in results:
        page = page_url_of(r)
        fp = fingerprint_result(page, r)
        if fp not in seen_links:
            seen_links.add(fp)
            current_fps.append(fp)
        if fp in seen_findings:
            continue
        for finding in collect_findings(page, [r], now=now):
            seen_findings.add(finding.fingerprint)
            current_findings.append(finding)

    diff = diff_findings(previous_findings, current_findings, now=now)
    link_counts = diff_link_counts(previous_fps, current_fps)
    _annotate_results(results, page_url_of, diff, now)

    return (diff, link_counts, now, site_id, current_findings, current_fps,
            baseline_status)


async def _resolve_site_id(saved: dict, site_id, site_url: str, user_email: str):
    """The site row may have been created by save_scan moments ago.

    _run_diff looks the site up *before* the upsert, so on a site's first scan it
    finds nothing. If save_scan then failed (or timed out) we have no id from it
    either — but the upsert may still have landed. Ask once more before giving up.
    """
    resolved = saved.get("site_id") or site_id
    if resolved:
        return resolved
    try:
        resolved = await get_site_id(site_url, user_email)
        if resolved:
            print(f"[Persist] recovered site_id={resolved} via post-save lookup")
        return resolved
    except Exception as e:
        print(f"[Persist] post-save site_id lookup failed: {type(e).__name__}: {e}")
        return None


async def _persist_snapshot(site_id, scan_id, diff, link_counts,
                            current_findings, current_fps, health_score,
                            redirect_rules=None, saved=None,
                            detected_builders=None) -> None:
    if not site_id:
        # Never silent. A skipped snapshot means no baseline next scan, and this
        # used to be the one path that produced zero rows and zero explanation.
        print(f"[Persist] SKIPPED snapshot: site_id=None scan_id={scan_id} — "
              f"save_scan result was {saved!r}")
        raise RuntimeError(
            "snapshot skipped: no site_id (save_scan returned no row and the "
            "post-save lookup found none)"
        )
    totals = {
        "health_score": health_score,
        "total_links": len(current_fps),
        "findings": len(current_findings),
        "new": len(diff.new),
        "fixed": len(diff.fixed),
        "recurring": len(diff.recurring),
        "new_links": link_counts.get("new_links"),
        "link_fingerprints": current_fps,
        # Collapsed first-hop -> final-destination rules, so the redirect-rules
        # endpoint can serve a ruleset without rescanning.
        "redirect_rules": redirect_rules or [],
        # The Fix Pack needs to know which builder's instructions to render.
        "detected_builders": detected_builders or [],
    }
    # Recurring findings must persist with their ORIGINAL first_seen_at, or age
    # resets every scan and "broken for 12 days" never happens.
    rows = [f.model_dump() for f in diff.new + diff.recurring]
    resolved = [(f.fingerprint, f.resolved_at) for f in diff.fixed]

    print(f"[Persist] saving snapshot: site_id={site_id} scan_id={scan_id} "
          f"findings={len(rows)} fingerprints={len(current_fps)}")
    await save_snapshot(site_id, scan_id, totals, rows, resolved)


def _breakdowns(results: list, site_url: str = "") -> dict:
    """Informational overview panels: Link Types, Top Hosts, Link Schemes, Redirects."""
    return {
        "link_types": link_type_breakdown(results),
        "top_hosts": host_breakdown(results),
        "schemes": scheme_breakdown(results),
        "redirects": redirect_summary(results, site_url),
    }


def _calculate_health_score(results: list) -> int:
    total = len(results)
    if total == 0:
        return 100

    def get(r, field):
        return r.get(field) if isinstance(r, dict) else getattr(r, field, None)

    # HTTP-ok but unverifiable (e.g. a #section we could not confirm) is not
    # a working link — it must not inflate the numerator.
    ok = sum(
        1 for r in results
        if get(r, "label") == "ok" and (get(r, "bucket") or "ok") == "ok"
    )
    broken_penalty = sum(3 for r in results if get(r, "label") == "broken")
    # Only high/medium-confidence dead CTAs cost health. Low-confidence
    # candidates land in the "unverifiable" bucket and must not be scored as
    # defects — we cannot prove they are broken.
    dead_cta_penalty = sum(
        2 for r in results
        if get(r, "label") == "dead_cta" and get(r, "bucket") == "dead_cta"
    )
    timeout_penalty = sum(1 for r in results if get(r, "label") == "timeout")
    score = round((ok / total) * 100) - broken_penalty - dead_cta_penalty - timeout_penalty
    return max(0, min(100, score))


def calculate_business_impact(
    label: str,
    category: str,
    days_broken: int = 0,
) -> dict:
    score = 0

    # Zone weight
    zone_weights = {
        "CTA": 40,
        "Navigation": 30,
        "Header": 25,
        "Body text": 15,
        "Footer": 10,
        "Other": 5,
        "Dead CTA": 35,
    }
    score += zone_weights.get(category, 5)

    # How long broken
    if days_broken > 14:
        score += 30
    elif days_broken > 7:
        score += 20
    elif days_broken > 3:
        score += 15
    elif days_broken > 1:
        score += 10
    else:
        score += 5

    # Label weight
    if label == "broken":
        score += 30
    elif label == "dead_cta":
        score += 25
    elif label == "error":
        score += 20

    # Classify
    if score >= 80:
        return {
            "score": score,
            "level": "Critical",
            "color": "#f87171",
            "description": "Fix immediately \u2014 high traffic area",
        }
    elif score >= 55:
        return {
            "score": score,
            "level": "High",
            "color": "#fb923c",
            "description": "Fix this week",
        }
    elif score >= 30:
        return {
            "score": score,
            "level": "Medium",
            "color": "#fbbf24",
            "description": "Fix when convenient",
        }
    else:
        return {
            "score": score,
            "level": "Low",
            "color": "#94a3b8",
            "description": "Low priority",
        }


# ─────────────────────────────────────────────────────────────────────────────
# The scan pipeline, once, with two consumers.
#
# It used to live inside the /scan SSE generator, so the only way to run a scan
# was to stream it to a browser. Monitoring needs the same pipeline server-side:
# same scrape, same checker, same form audit, same diff, same snapshot. Forking
# it would mean two definitions of "a scan" drifting apart.
#
# So it yields events instead of SSE frames. /scan encodes them; the monitor
# drains them and keeps the outcome. Identical bytes on the wire either way.
#
# `notify` exists because the two consumers alert differently: an interactive
# scan always posts to Slack, monitoring posts only when something changed.
# ─────────────────────────────────────────────────────────────────────────────
class ScanOutcome:
    """Everything a caller could want from one scan, already computed."""

    def __init__(self, url, results, health_score, diff, diff_payload,
                 site_id, baseline_status, detected_builders, payload):
        self.url = url
        self.results = results
        self.health_score = health_score
        self.diff = diff                      # ScanDiff — FindingRecords, with buckets
        self.diff_payload = diff_payload      # the JSON-safe summary
        self.site_id = site_id
        self.baseline_status = baseline_status
        self.detected_builders = detected_builders
        self.payload = payload                # exactly what /scan streams


def _progress(message: str, percent: int) -> tuple:
    return ("progress", {"type": "progress", "message": message, "percent": percent})


async def scan_events(url: str, email: str = "anonymous", notify: bool = True):
    """Yields ("progress", dict) … then ("result", ScanOutcome) or ("error", dict)."""
    try:
        yield _progress("Launching headless browser...", 5)
        await asyncio.sleep(0.1)

        links, detected_builders, signals = await scrape_links(url)
        yield _progress(f"Found {len(links)} links. Checking each one...", 30)
        await asyncio.sleep(0.1)

        results = []
        total = len(links)

        if total == 0:
            empty_diff = {
                "has_baseline": False,
                "baseline_status": BASELINE_FIRST_SCAN,
                "summary": summarize_diff(diff_findings(None, [])),
                "new": 0, "fixed": 0, "recurring": 0,
                "new_links": None, "removed_links": None, "fixed_findings": [],
            }
            payload = {"type": "result", "data": [], "health_score": 100,
                       "detected_builders": detected_builders,
                       "diff": empty_diff, **_breakdowns([], url)}
            yield ("result", ScanOutcome(
                url=url, results=[], health_score=100,
                diff=diff_findings(None, []), diff_payload=empty_diff,
                site_id=None, baseline_status=BASELINE_FIRST_SCAN,
                detected_builders=detected_builders, payload=payload))
            return

        async for i, result in check_all_links(links):
            results.append(result)
            pct = 30 + int((i / total) * 55)
            yield _progress(f"Checked {i}/{total} links...", pct)

        # A broken form is invisible: the page looks fine and the lead
        # vanishes. Audited passively — nothing is ever submitted — and fed
        # into the same results list, so it diffs and scores like any other
        # finding.
        # A 404 on a GET does not prove a POST-only endpoint is gone. Ask with
        # OPTIONS before accusing. OPTIONS is not a submission.
        signals["action_options"] = await probe_action_methods(results)
        results.extend(audit_forms(signals.get("forms"), results, signals, url))

        # Tracking & pixel integrity — passive, never `broken`. Uses the checked
        # results' redirect_chain for UTM survival, so no new request. Optional
        # per-site expected ids let it flag a page pointing at the wrong account.
        expected = await _expected_tracking(url, email)
        results.extend(audit_tracking(signals, results, url, expected=expected))

        # Per-page third-party integrations, from the SAME results + tracking
        # signals (one detection pass). Collected here while both are in hand;
        # persisted with the scan_id once it is known, below.
        page_integrations = collect_integrations(results, signals, url)

        # A third-party embed whose HOST is down is the provider's outage, not a
        # broken link on the client's site. Demote it to unverifiable so it never
        # turns their report red or dents their health score — the watchdog
        # raises the outage separately. Runs before the diff and health score so
        # the demoted verdict is what they see.
        demote_third_party_failures(results, url)

        # Explain dead CTAs with what actually failed on the page. Only ever
        # appends to `reason` — never changes bucket or confidence.
        enrich_reasons(results, signals)

        # Run suggestion engine
        actionable_count = sum(1 for r in results if r.label in ["broken", "dead_cta", "blocked"])
        if actionable_count > 0:
            yield _progress(f"Analyzing {actionable_count} links for suggestions...", 90)
            await asyncio.sleep(0.1)
            results = await process_suggestions(results)

        # Calculate business impact for actionable links
        for r in results:
            if r.label in ["broken", "dead_cta", "error"]:
                r.impact = calculate_business_impact(
                    label=r.label,
                    category=r.category,
                    days_broken=0,
                )

        # Calculate health score
        health_score = _calculate_health_score(results)

        # Diff against the previous snapshot. Runs before save_scan so it
        # reads the *previous* baseline, and annotates each flagged result
        # with fingerprint / diff_status / age_days.
        (diff, link_counts, now, site_id, current_findings, current_fps,
         baseline_status) = await _run_diff(url, email, results, lambda r: url)

        # Save to Supabase (non-blocking — never fail the scan)
        saved = {}
        effective_site_id = site_id
        try:
            saved = await save_scan(
                site_url=url,
                user_email=email,
                results=results,
                health_score=health_score,
            ) or {}
        except Exception as db_err:
            print(f"[DB] Save failed (non-critical): {db_err}")

        try:
            effective_site_id = await _resolve_site_id(saved, site_id, url, email)
            await _persist_snapshot(
                effective_site_id, saved.get("scan_id"),
                diff, link_counts, current_findings, current_fps, health_score,
                redirect_rules=collapse_rules(results, url),
                saved=saved,
                detected_builders=detected_builders,
            )
        except Exception as db_err:
            # The scan still succeeds, but the next one will have no baseline.
            print(f"[DB] Snapshot save failed: {describe_exception(db_err)}")
            baseline_status = BASELINE_UNAVAILABLE

        # Watchdog: record this scan's third-party hosts, and if any is down,
        # aggregate across every site and alert once. Best-effort — a watchdog
        # failure never touches the scan.
        await _run_watchdog_after_scan(effective_site_id, results, url)

        # Persist per-page integrations under this scan, then background-check any
        # resource the scan did not already health-check. Never blocks the stream.
        await _persist_and_check_integrations(saved.get("scan_id"), url, page_integrations)

        diff_payload = _diff_payload(diff, link_counts, now, baseline_status)

        # An interactive scan always reports. Monitoring alerts only on change,
        # so it drives notification itself: see monitoring.run_monitored_scan.
        if notify:
            await send_slack_notification(
                url, health_score, results, diff_summary=diff_payload["summary"]
            )

        # "14 unique links across 47 placements" — the same URL linked from
        # nav and footer is fetched once but counted in both places.
        total_placements = sum(getattr(r, "occurrences", 1) or 1 for r in results)

        payload = {"type": "result", "data": [r.dict() for r in results],
                   "health_score": health_score,
                   "detected_builders": detected_builders,
                   "total_links": len(results),
                   "total_placements": total_placements,
                   "diff": diff_payload, "site_id": effective_site_id,
                   "scan_id": saved.get("scan_id"), "scanned_url": url,
                   **_breakdowns(results, url)}
        yield ("result", ScanOutcome(
            url=url, results=results, health_score=health_score, diff=diff,
            diff_payload=diff_payload, site_id=effective_site_id,
            baseline_status=baseline_status,
            detected_builders=detected_builders, payload=payload))

    except Exception as e:
        yield ("error", {"type": "error", "message": str(e)})


async def run_scan_once(url: str, email: str = "anonymous") -> ScanOutcome:
    """The same pipeline, drained server-side. No SSE, no browser streaming.

    Monitoring calls this. It raises what the scan raised, rather than encoding
    the failure into an event nobody reads.
    """
    async for kind, event in scan_events(url, email, notify=False):
        if kind == "result":
            return event
        if kind == "error":
            raise RuntimeError(event.get("message") or "scan failed")
    raise RuntimeError("scan produced no result")


@app.get("/scan")
async def scan(
    url: str = Query(..., description="URL to scan"),
    email: str = Query(default="anonymous", description="User email for monitoring"),
    _acc: dict = Depends(require_role("member")),
):
    async def event_stream():
        async for kind, event in scan_events(url, email):
            frame = event.payload if kind == "result" else event
            yield f"data: {json.dumps(frame)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/scan-site")
async def scan_site(
    url: str = Query(..., description="Base site URL to scan, e.g. https://example.com"),
    email: str = Query(default="anonymous"),
    max_pages: int = Query(default=50, le=200),
    _acc: dict = Depends(require_role("member")),
):
    async def event_stream():
        try:
            yield f"data: {json.dumps({'type': 'progress', 'message': 'Discovering pages via sitemap or crawl...', 'percent': 5})}\n\n"
            await asyncio.sleep(0.1)

            discovered_pages = await discover_site_urls(url, max_pages)
            if not discovered_pages:
                yield f"data: {json.dumps({'type': 'progress', 'message': 'No pages discovered. Scraping homepage...', 'percent': 10})}\n\n"
                discovered_pages = [url]

            total_pages = len(discovered_pages)
            yield f"data: {json.dumps({'type': 'progress', 'message': f'Discovered {total_pages} pages. Starting scan...', 'percent': 15})}\n\n"
            await asyncio.sleep(0.1)

            # The site's expected tracking ids, read once for the whole crawl.
            site_expected = await _expected_tracking(url, email)

            sem = asyncio.Semaphore(5)
            queue = asyncio.Queue()
            completed_pages = 0
            all_results = []
            site_integrations = {}   # page_url -> [integration records], persisted after save
            # Builders seen anywhere on the site, in first-seen order.
            site_builders: list[str] = []

            async def scan_page_worker(page_url: str):
                nonlocal completed_pages
                async with sem:
                    # Emit status update: starting scan
                    from urllib.parse import urlparse
                    path_to_show = urlparse(page_url).path or "/"
                    await queue.put({
                        "type": "progress",
                        "message": f"Scanning page {completed_pages + 1}/{total_pages}: {path_to_show}"
                    })
                    try:
                        links, page_builders, page_signals = await scrape_links(page_url)
                        for b in page_builders:
                            if b not in site_builders:
                                site_builders.append(b)
                        page_results = []
                        if links:
                            async for i, res in check_all_links(links):
                                page_results.append(res)

                            page_signals["action_options"] = \
                                await probe_action_methods(page_results)
                            page_results.extend(audit_forms(
                                page_signals.get("forms"), page_results,
                                page_signals, page_url,
                            ))
                            page_results.extend(audit_tracking(
                                page_signals, page_results, page_url,
                                expected=site_expected,
                            ))
                            demote_third_party_failures(page_results, page_url)

                            # Per-page integrations (same results + tracking).
                            site_integrations[page_url] = collect_integrations(
                                page_results, page_signals, page_url)

                            # Console/request failures are per page.
                            enrich_reasons(page_results, page_signals)

                            actionable_count = sum(1 for r in page_results if r.label in ["broken", "dead_cta", "blocked"])
                            if actionable_count > 0:
                                page_results = await process_suggestions(page_results)

                        # Convert and enrich
                        serialized = []
                        for r in page_results:
                            rd = r.dict()
                            rd["found_on_page"] = page_url
                            if r.label in ["broken", "dead_cta", "error"]:
                                rd["impact"] = calculate_business_impact(
                                    label=r.label,
                                    category=r.category,
                                    days_broken=0,
                                )
                            serialized.append(rd)

                        completed_pages += 1
                        pct = 15 + int((completed_pages / total_pages) * 75)
                        await queue.put({
                            "type": "progress",
                            "message": f"Scanned page {completed_pages}/{total_pages}: {path_to_show}",
                            "percent": pct
                        })
                        await queue.put({"type": "data", "results": serialized})
                    except Exception as page_err:
                        print(f"[ScanSite] Error scanning page {page_url}: {page_err}")
                        completed_pages += 1
                        pct = 15 + int((completed_pages / total_pages) * 75)
                        await queue.put({
                            "type": "progress",
                            "message": f"Failed page {completed_pages}/{total_pages}: {path_to_show}",
                            "percent": pct
                        })

            # Launch all workers
            tasks = [asyncio.create_task(scan_page_worker(p)) for p in discovered_pages]

            # Read from the queue and stream progress/data
            from urllib.parse import urlparse
            while completed_pages < total_pages or not queue.empty():
                try:
                    # Non-blocking check to retrieve queued events
                    msg = await asyncio.wait_for(queue.get(), timeout=0.1)
                    if msg["type"] == "progress":
                        yield f"data: {json.dumps({'type': 'progress', 'message': msg['message'], 'percent': msg.get('percent', 15)})}\n\n"
                    elif msg["type"] == "data":
                        all_results.extend(msg["results"])
                except asyncio.TimeoutError:
                    if completed_pages >= total_pages and queue.empty():
                        break
                    await asyncio.sleep(0.05)

            # Ensure all workers are joined
            await asyncio.gather(*tasks, return_exceptions=True)

            # Deduplicate results at target URL level
            # Store all found_on_pages
            deduped = {}
            for r in all_results:
                r_url = r["url"]
                found_page = r.get("found_on_page") or url
                
                # Normalize path for readability in found_on_pages
                parsed_found = urlparse(found_page)
                page_path = parsed_found.path or "/"
                if parsed_found.query:
                    page_path += f"?{parsed_found.query}"

                if r_url not in deduped:
                    r["found_on_pages"] = [page_path]
                    deduped[r_url] = r
                else:
                    if page_path not in deduped[r_url]["found_on_pages"]:
                        deduped[r_url]["found_on_pages"].append(page_path)

            final_results = list(deduped.values())
            health_score = _calculate_health_score(final_results)

            # Findings are identified per page they were found on.
            (diff, link_counts, now, site_id, current_findings, current_fps,
             baseline_status) = await _run_diff(
                url, email, final_results,
                lambda r: r.get("found_on_page") or url,
            )

            # Save full site scan to Supabase (non-blocking)
            saved = {}
            effective_site_id = site_id
            try:
                saved = await save_scan(
                    site_url=url,
                    user_email=email,
                    results=final_results,
                    health_score=health_score,
                    pages_scanned=total_pages,
                ) or {}
            except Exception as db_err:
                print(f"[DB] Save site scan failed (non-critical): {db_err}")

            try:
                effective_site_id = await _resolve_site_id(saved, site_id, url, email)
                await _persist_snapshot(
                    effective_site_id, saved.get("scan_id"),
                    diff, link_counts, current_findings, current_fps, health_score,
                    redirect_rules=collapse_rules(final_results, url),
                    saved=saved,
                    detected_builders=site_builders,
                )
            except Exception as db_err:
                print(f"[DB] Snapshot save failed: {describe_exception(db_err)}")
                baseline_status = BASELINE_UNAVAILABLE

            # Watchdog across the whole crawl's third-party hosts.
            await _run_watchdog_after_scan(effective_site_id, final_results, url)

            # Persist every page's integrations under this scan, and background-
            # check any resource not already health-checked.
            for p_url, recs in site_integrations.items():
                await _persist_and_check_integrations(saved.get("scan_id"), p_url, recs)

            diff_payload = _diff_payload(diff, link_counts, now, baseline_status)

            # Send Slack notification
            class SimpleNamespace:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)
            slack_results = [SimpleNamespace(**r) for r in final_results]
            await send_slack_notification(
                url, health_score, slack_results, diff_summary=diff_payload["summary"]
            )

            # Yield final result event
            total_placements = sum(r.get("occurrences", 1) or 1 for r in final_results)

            yield f"data: {json.dumps({'type': 'result', 'data': final_results, 'health_score': health_score, 'pages_scanned': total_pages, 'detected_builders': site_builders, 'total_links': len(final_results), 'total_placements': total_placements, 'diff': diff_payload, 'site_id': effective_site_id, 'scan_id': saved.get('scan_id'), 'scanned_url': url, **_breakdowns(final_results, url)})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/sites/{site_id}/diff/latest")
async def latest_diff(site_id: str, _acc: dict = Depends(require_site_access("client_viewer"))):
    """Diff the two most recent snapshots for a site.

    Stateless: recomputed from stored findings rather than trusting counters.
    A site with fewer than two snapshots has no baseline — the UI shows n/a
    rather than reporting every pre-existing issue as new.
    """
    try:
        snapshots = await get_recent_snapshots(site_id, limit=2)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    if not snapshots:
        return {
            "site_id": site_id,
            "has_baseline": False,
            "summary": "No scans yet",
            "new": 0, "fixed": 0, "recurring": 0,
            "new_links": None, "removed_links": None,
            "items": {"new": [], "recurring": [], "fixed": []},
        }

    latest = snapshots[0]
    previous = snapshots[1] if len(snapshots) > 1 else None

    current_findings = _findings_from_rows(await get_findings_for_snapshot(latest["id"]))
    previous_findings = (
        _findings_from_rows(await get_findings_for_snapshot(previous["id"]))
        if previous else None
    )

    now = utcnow_iso()
    diff = diff_findings(previous_findings, current_findings, now=now)
    link_counts = diff_link_counts(
        (previous.get("totals_json") or {}).get("link_fingerprints") if previous else None,
        (latest.get("totals_json") or {}).get("link_fingerprints") or [],
    )

    return {
        "site_id": site_id,
        "scanned_at": latest.get("created_at"),
        **{k: v for k, v in _diff_payload(diff, link_counts, now).items()
           if k != "fixed_findings"},
        "items": {
            "new": [_finding_payload(f, now) for f in diff.new],
            "recurring": [_finding_payload(f, now) for f in diff.recurring],
            "fixed": [_finding_payload(f, now) for f in diff.fixed],
        },
    }


@app.get("/api/diagnostics/diffing")
async def diffing_diagnostics(
    url: str = Query(default="", description="Optional: report storage for this site"),
    email: str = Query(default="anonymous"),
    _acc: dict = Depends(require_role("member")),
):
    """Is scan storage actually working?

    Diffing needs the tables from backend/migrations/001; History needs rows in
    `scans`. Both used to fail silently. Pass ?url= to see exactly how much of a
    given site reached storage.
    """
    try:
        checks = await diffing_tables_ready()
    except Exception as e:
        return {
            "diffing_ready": False,
            "checks": {},
            "error": f"{type(e).__name__}: {e}",
            "migration": "backend/migrations/001_phase1_snapshots_findings.sql",
        }

    ready = all(status == "ok" for status in checks.values())
    body = {
        "diffing_ready": ready,
        "checks": checks,
        "migration": "backend/migrations/001_phase1_snapshots_findings.sql",
    }
    if not ready:
        body["hint"] = (
            "Apply backend/migrations/001_phase1_snapshots_findings.sql to the "
            "Supabase project, then rescan twice: the first scan writes the "
            "baseline, the second one diffs against it."
        )

    if url:
        try:
            body["site"] = await site_storage_report(url, email)
        except Exception as e:
            body["site"] = {"error": describe_exception(e)}

    # The real PostgREST error from the last failed snapshot write, if any.
    # A SELECT can succeed while an INSERT is refused (row-level security),
    # and reads alone cannot tell those apart.
    body["last_snapshot_error"] = last_snapshot_error()
    return body


@app.get("/api/diagnostics/snapshot-write-test")
async def snapshot_write_test(
    url: str = Query(..., description="A site URL that has already been scanned"),
    email: str = Query(default="anonymous"),
    _acc: dict = Depends(require_role("member")),
):
    """Attempt a real snapshot + finding write, then delete both.

    Reads succeeding while writes fail is the signature of row-level security
    with no policy. This performs the write and returns the full PostgREST
    error, then cleans up the probe rows it created.
    """
    try:
        return await snapshot_write_probe(url, email)
    except Exception as e:
        return JSONResponse(
            {"ok": False, "stage": "probe", "error": describe_exception(e)},
            status_code=500,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 6 — fix engine
# ─────────────────────────────────────────────────────────────────────────────
def _snapshot_context(snapshot: dict) -> tuple:
    totals = (snapshot or {}).get("totals_json") or {}
    # Contradictory detection means at least one builder is wrong. choose_builder
    # falls back to generic rather than sending a client into the wrong editor.
    builder = choose_builder(totals.get("detected_builders") or [])
    return builder, totals.get("redirect_rules") or []


@app.get("/api/sites/{site_id}/fix-pack")
async def fix_pack(site_id: str, _acc: dict = Depends(require_site_access("member"))):
    """A zip the operator opens and works through: fixes.csv, instructions.md,
    and the redirect ruleset."""
    try:
        snapshot = await get_latest_snapshot(site_id)
        site_url = await get_site_url(site_id) or ""
    except Exception as e:
        return JSONResponse({"error": describe_exception(e)}, status_code=500)

    if not snapshot:
        return JSONResponse(
            {"error": "no scan snapshot for this site yet — run a scan first"},
            status_code=404,
        )

    try:
        findings = await get_findings_for_snapshot(snapshot["id"])
    except Exception as e:
        return JSONResponse({"error": describe_exception(e)}, status_code=500)

    builder, redirect_rules = _snapshot_context(snapshot)

    # Working URLs on the site are the candidate pool a 404'd link is matched
    # against. Without them the engine proposes nothing, which is correct.
    site_urls = [f.get("url") for f in findings if f.get("bucket") == "ok"]

    rows = build_rows(
        [{**f, "page_url": site_url} for f in findings if f.get("bucket") != "ok"],
        builder, site_url, site_urls=site_urls,
    )
    body = build_fix_pack(rows, site_url=site_url, builder=builder,
                          redirect_rules=redirect_rules)

    filename = "linkspy-fix-pack.zip"
    return Response(
        content=body,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/findings/{finding_id}/fix")
async def finding_fix(finding_id: str, builder: str = Query(default=""),
                      site_id: str = Query(default=""),
                      _acc: dict = Depends(require_finding_access("member"))):
    """The "How to fix" panel: hand-authored steps for this finding."""
    try:
        finding = await get_finding(finding_id, site_id)
    except Exception as e:
        return JSONResponse({"error": describe_exception(e)}, status_code=500)
    if not finding:
        return JSONResponse({"error": "finding not found"}, status_code=404)

    site_url = await get_site_url(finding["site_id"]) or ""
    suggestion = build_fix_suggestion(finding, builder, page_url=site_url)
    return suggestion.model_dump()


@app.get("/api/findings/{finding_id}/client-message")
async def finding_client_message(finding_id: str, site_id: str = Query(default=""),
                                 _acc: dict = Depends(require_finding_access("member"))):
    """Copy-pasteable client message. Every value is HTML-escaped."""
    try:
        finding = await get_finding(finding_id, site_id)
    except Exception as e:
        return JSONResponse({"error": describe_exception(e)}, status_code=500)
    if not finding:
        return JSONResponse({"error": "finding not found"}, status_code=404)

    site_url = await get_site_url(finding["site_id"]) or ""
    age = issue_age_days(finding.get("first_seen_at"), utcnow_iso())
    age_phrase = (
        f"It has been like this for {age} day{'s' if age != 1 else ''}."
        if age else ""
    )
    return render_client_message(finding, page_url=site_url, site_url=site_url,
                                 age_phrase=age_phrase)


@app.post("/api/findings/{finding_id}/verify")
async def verify_fix(finding_id: str, site_id: str = Query(default=""),
                     _acc: dict = Depends(require_finding_access("member"))):
    """Re-check one finding live.

    Flips to "verified_fixed" only on a clean check. If it is still broken, it
    says so — the point of this endpoint is that it does not take anyone's word.
    """
    try:
        finding = await get_finding(finding_id, site_id)
    except Exception as e:
        return JSONResponse({"error": describe_exception(e)}, status_code=500)
    if not finding:
        return JSONResponse({"error": "finding not found"}, status_code=404)

    outcome = await verify_finding(finding)

    if outcome["verified"]:
        resolved_at = utcnow_iso()
        try:
            await mark_finding_verified(finding["id"], resolved_at)
            outcome["resolved_at"] = resolved_at
        except Exception as e:
            # The check passed but the write did not. Do not claim it is saved.
            outcome["verified"] = False
            outcome["status"] = finding.get("status", "open")
            outcome["reason"] = (
                "The link is fixed, but recording that failed: "
                f"{describe_exception(e).get('message') or describe_exception(e)['str']}"
            )

    return {"finding_id": finding_id, **outcome}


@app.get("/api/sites/{site_id}/redirect-rules")
async def redirect_rules(
    site_id: str,
    format: str = Query("cloudflare", description="cloudflare | netlify | htaccess"),
    _acc: dict = Depends(require_site_access("member")),
):
    """Collapsed redirect ruleset (first hop -> final destination) for a site.

    Rules were derived from scanned page content, so every URL is re-validated
    and escaped for the requested format before it reaches the file.
    """
    if format not in FORMATS:
        return JSONResponse(
            {"error": f"unknown format {format!r}", "supported": sorted(FORMATS)},
            status_code=400,
        )

    try:
        snapshot = await get_latest_snapshot(site_id)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    rules = ((snapshot or {}).get("totals_json") or {}).get("redirect_rules") or []
    media_type, filename, body = render(format, rules)

    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/history")
async def history(
    url: str = Query(..., description="Site URL"),
    email: str = Query(default="anonymous", description="User email"),
    _acc: dict = Depends(require_role("member")),
):
    """Get scan history for a site."""
    try:
        from database import get_site_history
        data = await get_site_history(url, email)
        return {"url": url, "history": data}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/register")
async def register(
    url: str = Query(..., description="Site URL to track"),
    email: str = Query(..., description="User email"),
    _acc: dict = Depends(require_role("member")),
):
    """Register a site for tracking."""
    from database import _get_client
    import asyncio as _asyncio

    def _register():
        client = _get_client()
        client.table("sites").upsert({
            "url": url,
            "user_email": email,
        }, on_conflict="url,user_email").execute()
        return {"registered": True}

    try:
        result = await _asyncio.to_thread(_register)
        return result
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/uptime")
async def uptime(url: str = Query(...), _acc: dict = Depends(require_role("member"))):
    try:
        from database import get_uptime
        data = await get_uptime(url)
        return {"url": url, "issues": data}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/dashboard")
async def dashboard_data(_acc: dict = Depends(require_role("client_viewer"))):
    import asyncio as _asyncio

    # Scope-aware: a member+ sees all workspace sites (or all sites when
    # enforcement is off — today's behavior); a client_viewer sees only the
    # sites of their assigned client.
    role = _acc.get("role")
    workspace_id = _acc.get("workspace_id")
    client_id = _acc.get("client_id")

    def _get_dashboard():
        from database import _get_client
        client = _get_client()
        q = client.table("sites")\
            .select("*, scans(id, scanned_at, total_links, broken_count, dead_cta_count, health_score)")
        if role == "client_viewer":
            q = q.eq("workspace_id", workspace_id).eq("client_id", client_id)
        elif workspace_id:  # enforced member/owner -> scope to their workspace
            q = q.eq("workspace_id", workspace_id)
        # enforcement off (workspace_id None, role owner) -> unscoped, as today
        sites = q.order("last_scanned_at", desc=True).execute()
        return sites.data

    try:
        data = await _asyncio.to_thread(_get_dashboard)
        return {"sites": data}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/sites")
async def add_site_endpoint(site: SiteCreate, _acc: dict = Depends(require_role("member"))):
    try:
        from database import add_site
        await add_site(site.url, site.name, site.client, site.freq, site.user_email)
        return {"status": "success"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/sites/{site_id}")
async def delete_site_endpoint(site_id: str, _acc: dict = Depends(require_site_access("member"))):
    try:
        from database import delete_site
        await delete_site(site_id)
        return {"status": "success"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ─── monitoring endpoints ────────────────────────────────────────────────────
@app.post("/api/sites/{site_id}/monitoring")
async def set_site_monitoring(site_id: str, enabled: bool = Query(...),
                              freq: str = Query(default=""),
                              _acc: dict = Depends(require_site_access("member"))):
    """Turn monitoring on/off for a site and (re)schedule it live.

    The scheduler is updated in the same request, so a toggle takes effect
    without waiting for a restart.
    """
    from database import MonitoringColumnMissing
    try:
        await set_monitoring(site_id, enabled, freq or None)
        site = await get_site(site_id)
        if not site:
            return JSONResponse({"error": "site not found"}, status_code=404)
        if enabled:
            _scheduler.schedule_site(site)
            if _scheduler._scheduler and not _scheduler._scheduler.running:
                _scheduler.start()
        else:
            _scheduler.unschedule_site(site_id)
        return {"status": "ok", "monitoring_enabled": enabled,
                "freq": site.get("freq")}
    except MonitoringColumnMissing as e:
        # Not a server fault — a setup step. Say exactly what to run, so the
        # toggle does not just silently snap back to off.
        return JSONResponse({"error": str(e), "setup_required": True},
                            status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/sites/{site_id}/monitoring")
async def site_monitoring_status(site_id: str, _acc: dict = Depends(require_site_access("member"))):
    """The uptime record: last checked, current health, healthy streak, events."""
    try:
        snapshots = await get_recent_snapshots(site_id, limit=60)
        status = monitoring_status(snapshots)
        status["digest"] = weekly_digest(snapshots)
        site = await get_site(site_id)
        # Return a canonical cadence, so the panel highlights the right button
        # even for a legacy site stored as "Every Hour" rather than "hourly".
        status["freq"] = monitoring.normalize_cadence((site or {}).get("freq"))
        status["monitoring_enabled"] = bool((site or {}).get("monitoring_enabled"))
        return status
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/sites/{site_id}/monitoring/run-now")
async def run_monitoring_check_now(site_id: str, _acc: dict = Depends(require_site_access("member"))):
    """Run the real monitored-scan path once, right now, and report what it
    decided. This is the exact code the scheduler runs — same scan, same diff,
    same change-only alert rule — with the duplicate-fire window skipped so a
    manual test always executes. Lets you verify monitoring end to end without
    waiting for the cadence.
    """
    try:
        site = await get_site(site_id)
        if not site:
            return JSONResponse({"error": "site not found"}, status_code=404)
        result = await run_monitored_scan(
            site, run_scan=run_scan_once, get_last_snapshot=get_latest_snapshot,
            recheck_link=_recheck_link, notify=_notify_change,
            skip_guard=True,
        )
        # Plain-language reading of the decision, for the UI.
        explain = {
            "scanned_no_change": "Ran a full check. Nothing changed since the "
                                 "last scan, so no alert was sent — this is the "
                                 "healthy, silent case.",
            "scanned_alerted": "Ran a full check and found a change. An alert "
                               "was sent.",
            "skipped_too_soon": "A scan ran very recently, so this was skipped.",
        }.get(result.get("status"), "Check complete.")
        return {**result, "explanation": explain, "ran_at": utcnow_iso()}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/sites/{site_id}/tracking-ids")
async def set_site_tracking_ids(site_id: str, ga4: str = Query(default=""),
                                meta_pixel: str = Query(default=""),
                                gtm: str = Query(default=""),
                                _acc: dict = Depends(require_site_access("member"))):
    """Store a site's own GA4 / Meta / GTM ids so the tracking audit can flag a
    page pointing at the wrong account. All optional; empty clears that id."""
    from database import MonitoringColumnMissing
    try:
        saved = await set_expected_tracking(
            site_id, {"ga4": ga4, "meta_pixel": meta_pixel, "gtm": gtm})
        return {"status": "ok", "expected_tracking": saved.get("expected_tracking")}
    except MonitoringColumnMissing as e:
        return JSONResponse({"error": str(e), "setup_required": True},
                            status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ─── Phase 10: self-heal auto-PR (MOST GUARDED — flag off + allowlist) ───────
@app.get("/api/self-heal/status")
async def self_heal_status(_acc: dict = Depends(require_role("member"))):
    """Whether self-heal is armed, and on which repos. Read-only, safe to call.
    Reflects only the flag and the allowlist — it never touches a repo."""
    from self_heal import self_heal_enabled, allowlist
    return {"enabled": self_heal_enabled(), "allowlist": sorted(allowlist())}


@app.post("/api/self-heal/run")
async def self_heal_run(repo: str = Query(...), scan_id: str = Query(...),
                        url: str = Query(...), fix_type: str = Query(default="redirect"),
                        _acc: dict = Depends(require_role("member"))):
    """Open PR(s) of PROVABLE fixes on an ALLOWLISTED repo. Refuses unless the
    SELF_HEAL flag is on AND the repo is on the allowlist. Never merges."""
    from self_heal import self_heal_enabled, is_allowed_repo
    # Rails 1 & 2, checked before any work (and before we even scan).
    if not self_heal_enabled():
        return JSONResponse({"error": "SELF_HEAL is off.", "refused": True}, status_code=403)
    if not is_allowed_repo(repo):
        return JSONResponse({"error": f"{repo} is not on the self-heal allowlist.",
                             "refused": True}, status_code=403)
    token = os.getenv("SELF_HEAL_GITHUB_TOKEN")
    if not token:
        return JSONResponse({"error": "No SELF_HEAL_GITHUB_TOKEN configured.",
                             "refused": True}, status_code=400)
    try:
        outcome = await run_scan_once(url, "self-heal")
        from self_heal_pr import run_self_heal
        from self_heal_github import GitHubRepoOps
        result = await run_self_heal(
            repo=repo, scan_id=scan_id, results=outcome.results,
            recheck=lambda u: _recheck_status(u), repo_ops=GitHubRepoOps(repo, token),
            now_iso=utcnow_iso(), fix_type=fix_type)
        return result
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def _recheck_status(url: str):
    """Status int for verify-before-PR, via the same single-link checker."""
    link = RawLink(url=url, source_element="a", anchor_text="", category="Other",
                   is_external=True, zones=["Other"], link_kind="http")
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        result = await check_single(client, link)
    return getattr(result, "status_code", None)


# ─── Phase 4: opt-in active form testing (DANGEROUS — every rail enforced) ───
@app.get("/api/sites/{site_id}/forms/optin")
async def list_active_form_optins(site_id: str, _acc: dict = Depends(require_site_access("member"))):
    """Which forms on this site are enabled for active testing, and their test
    email. Also reports whether the global flag is on, so the UI can explain why
    a test would refuse."""
    try:
        optins = await list_form_optins(site_id)
        return {"global_enabled": active_testing_enabled(), "forms": optins}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/sites/{site_id}/forms/optin")
async def set_active_form_optin(site_id: str, form_key: str = Query(...),
                                enabled: bool = Query(...),
                                test_email: str = Query(default=""),
                                _acc: dict = Depends(require_site_access("member"))):
    """Explicitly enable/disable active testing for ONE form. Enabling is a
    deliberate human action — nothing tests a form that has not been turned on
    here, and there is no bulk switch."""
    from database import MonitoringColumnMissing
    try:
        saved = await set_form_optin(site_id, form_key, enabled, test_email or None)
        return {"status": "ok", "form_key": form_key,
                "enabled": bool(saved.get("enabled", enabled)),
                "test_email": saved.get("test_email")}
    except MonitoringColumnMissing as e:
        return JSONResponse({"error": str(e), "setup_required": True}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/sites/{site_id}/forms/active-test")
async def run_active_form_test(site_id: str, form_key: str = Query(...),
                               form_selector: str = Query(...),
                               _acc: dict = Depends(require_site_access("member"))):
    """Submit ONE opted-in form ONCE, manually. This is the dangerous path, so
    it refuses unless BOTH rails pass: the global ACTIVE_FORM_TESTING flag is on
    AND this specific form is opted in. Payment forms are refused inside the
    executor regardless."""
    # Rail 1: the global kill-switch.
    if not active_testing_enabled():
        return JSONResponse(
            {"error": "Active form testing is turned off. Set ACTIVE_FORM_TESTING "
                      "on in the environment to enable it.", "refused": True},
            status_code=403)
    # Rail 2: this specific form must be opted in.
    optin = await get_form_optin(site_id, form_key)
    if not optin or not optin.get("enabled"):
        return JSONResponse(
            {"error": "This form is not enabled for active testing. Turn it on "
                      "for this form first — there is no bulk test.", "refused": True},
            status_code=403)

    site = await get_site(site_id)
    if not site:
        return JSONResponse({"error": "site not found"}, status_code=404)

    from active_submission_exec import submit_test_form
    try:
        record = await asyncio.to_thread(
            submit_test_form, site["url"], form_selector,
            test_email=optin.get("test_email"))
        return record
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


_HEALTH_SORT = {"down": 0, "unresponsive": 1, "checking": 2, "unknown": 3, "healthy": 4}


@app.get("/api/scans/{scan_id}/integrations")
async def scan_integrations(scan_id: str, page: str = Query(default=""),
                            _acc: dict = Depends(require_scan_access("client_viewer"))):
    """Third-party integrations for a scan. `page` (URL-encoded query param, so a
    slashy/query-string page URL survives) filters to one page; omit for all
    pages grouped. Sorted down first, then unresponsive, then by category."""
    try:
        rows = await get_integrations(scan_id, page or None)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    rows.sort(key=lambda r: (_HEALTH_SORT.get(r.get("health_status"), 5),
                             r.get("category") or "", r.get("host") or ""))
    if page:
        return {"page": page, "count": len(rows),
                "down": sum(1 for r in rows if r.get("health_status") == "down"),
                "integrations": rows}
    # Grouped by page when no filter.
    by_page = {}
    for r in rows:
        by_page.setdefault(r["page_url"], []).append(r)
    return {"pages": [{"page": p, "count": len(items),
                       "down": sum(1 for r in items if r.get("health_status") == "down"),
                       "integrations": items}
                      for p, items in by_page.items()],
            "total": len(rows)}


@app.get("/api/watchdog/hosts")
async def watchdog_hosts(_acc: dict = Depends(require_role("member"))):
    """Third-party host inventory across all sites, with per-host affected-site
    counts and last-known status. Down hosts (an outage in progress) first."""
    try:
        inventory = await get_watchdog_inventory()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    # Group every host (up and down) so the UI can show the full dependency map,
    # not only outages. aggregate_outages covers the down ones; do the rest here.
    by_host = {}
    for row in inventory:
        h = by_host.setdefault(row["host"], {
            "host": row["host"], "resource_type": row.get("resource_type"),
            "status": row.get("status"), "down": False, "sites": [],
        })
        h["sites"].append({"site_id": row.get("site_id"),
                           "site_url": row.get("site_url"),
                           "client": row.get("client")})
        if row.get("down"):
            h["down"] = True
            h["status"] = row.get("status")
    hosts = sorted(by_host.values(),
                   key=lambda h: (not h["down"], -len(h["sites"]), h["host"]))
    return {
        "hosts": [{**h, "affected_sites": len(h["sites"])} for h in hosts],
        "outages": len([h for h in hosts if h["down"]]),
        "total_hosts": len(hosts),
    }


@app.get("/preview")
async def preview(url: str = Query(..., description="URL to screenshot")):
    now = time.time()

    if url in _preview_cache:
        cached_b64, cached_at = _preview_cache[url]
        if now - cached_at < _PREVIEW_CACHE_TTL:
            return JSONResponse({
                "url": url,
                "screenshot": cached_b64,
                "cached": True,
            })

    try:
        b64_png = await asyncio.to_thread(_capture_screenshot, url)
        _preview_cache[url] = (b64_png, now)

        expired = [
            k for k, (_, t) in _preview_cache.items()
            if now - t >= _PREVIEW_CACHE_TTL
        ]
        for k in expired:
            del _preview_cache[k]

        return JSONResponse({
            "url": url,
            "screenshot": b64_png,
            "cached": False,
        })
    except Exception as e:
        return JSONResponse({"url": url, "error": str(e)}, status_code=500)


def _capture_screenshot(url: str) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=15000)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=10000)
            screenshot_bytes = page.screenshot(type="png")
            return base64.b64encode(screenshot_bytes).decode("utf-8")
        finally:
            browser.close()


# ─── Wave 1: X-ray view ──────────────────────────────────────────────────────
# On-demand full-page screenshot + clickable-element geometry. Deliberately NOT
# part of the scan render, so it is fully additive and can never break a scan.
_xray_cache: dict[str, tuple[dict, float]] = {}
_XRAY_CACHE_TTL = 180  # seconds


@app.get("/api/xray")
async def xray(url: str = Query(..., description="URL to capture for the X-ray overlay")):
    """A full-page screenshot plus the on-page box of every clickable element.
    Best-effort: returns {available: false} rather than erroring, so the report
    degrades to a plain findings list."""
    from xray import capture_xray_sync
    now = time.time()
    cached = _xray_cache.get(url)
    if cached and now - cached[1] < _XRAY_CACHE_TTL:
        return JSONResponse({**cached[0], "cached": True})
    data = await asyncio.to_thread(capture_xray_sync, url)
    if data.get("available"):
        _xray_cache[url] = (data, now)
        for k in [k for k, (_, t) in _xray_cache.items() if now - t >= _XRAY_CACHE_TTL]:
            _xray_cache.pop(k, None)
    return JSONResponse(data, status_code=200 if data.get("available") else 502)


# ─── Wave 1: shareable client report ─────────────────────────────────────────
@app.post("/api/scans/{scan_id}/share")
async def create_share(scan_id: str, _acc: dict = Depends(require_scan_access("member"))):
    """Mint an unguessable, revocable public link to this scan's report."""
    from sharing import new_token
    from database import create_share_token, ShareStorageMissing
    token = new_token()
    try:
        created = await create_share_token(scan_id, token)
    except ShareStorageMissing:
        return JSONResponse(
            {"error": "Report sharing isn't set up on the database yet. Apply "
                      "migration 008_share_tokens.sql in Supabase, then try again.",
             "setup_required": True},
            status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    if not created:
        return JSONResponse(
            {"error": "That scan couldn't be found — it may not have been saved. "
                      "Re-scan the page and try sharing again."},
            status_code=404)
    return {"token": token, "url": f"{_frontend_url()}/r/{token}", "path": f"/r/{token}"}


@app.delete("/api/share/{token}")
async def revoke_share(token: str):
    """Revoke a share link. The public URL 404s afterwards."""
    from sharing import is_wellformed
    from database import revoke_share_token
    if not is_wellformed(token):
        return JSONResponse({"error": "Malformed token."}, status_code=400)
    ok = await revoke_share_token(token)
    return {"revoked": bool(ok)}


@app.get("/api/r/{token}")
async def shared_report(token: str):
    """Public, read-only report behind a share token. No auth. 404 if the token
    is unknown or revoked."""
    from sharing import is_wellformed
    from database import get_shared_report
    if not is_wellformed(token):
        return JSONResponse({"error": "Not found."}, status_code=404)
    report = await get_shared_report(token)
    if not report:
        return JSONResponse({"error": "This report link is invalid or has been revoked."},
                            status_code=404)
    return report


# ─── Wave 1: embeddable status badge ─────────────────────────────────────────
@app.get("/api/sites/{site_id}/badge.svg")
async def site_badge(site_id: str):
    """A tiny score-colored SVG badge. Public, cacheable; updates after a rescan
    (short cache). Never scanned -> gray '--'."""
    from badge import build_badge_svg
    from database import get_latest_score
    score = None
    try:
        latest = await get_latest_score(site_id)
        if latest:
            score = latest.get("health_score")
    except Exception:
        score = None
    svg = build_badge_svg(score)
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=300, s-maxage=300",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ─── Wave 3 (detail standard): anticipatory scan pre-warm ────────────────────
# Cheap, idempotent DNS + first-byte warmup so a scan feels instant on click.
# Never scans, never renders — just primes the connection. Deduped by URL.
_prewarm_seen: dict[str, float] = {}
_PREWARM_TTL = 30  # seconds — don't re-warm the same URL within this window


@app.get("/api/prewarm")
async def prewarm(url: str = Query(..., description="URL the user is about to scan")):
    now = time.time()
    last = _prewarm_seen.get(url)
    if last and now - last < _PREWARM_TTL:
        return {"warmed": True, "cached": True}
    _prewarm_seen[url] = now
    for k in [k for k, t in _prewarm_seen.items() if now - t >= _PREWARM_TTL]:
        _prewarm_seen.pop(k, None)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=5) as client:
            try:
                await client.head(url)
            except Exception:
                # Some origins reject HEAD — a ranged GET still primes DNS/TLS.
                await client.get(url, headers={"Range": "bytes=0-0"})
        return {"warmed": True}
    except Exception as e:
        # Best-effort: a failed warmup must never block or error the UI.
        return JSONResponse({"warmed": False, "error": str(e)}, status_code=200)


# ─── Client portal: clients, invites, audit (agency side) ────────────────────
async def _acting_workspace(acc: dict):
    """The workspace a member is acting in — their membership's, or (enforcement
    off / owner bypass) the single Apexure workspace."""
    from database import staff_workspace_id
    return acc.get("workspace_id") or await staff_workspace_id()


@app.post("/api/clients")
async def create_client_endpoint(name: str = Query(...), _acc: dict = Depends(require_role("member"))):
    from database import create_client, write_audit
    ws = await _acting_workspace(_acc)
    if not ws:
        return JSONResponse({"error": "No workspace — run the multi-tenancy backfill first.",
                             "setup_required": True}, status_code=400)
    created = await create_client(ws, name.strip())
    if not created:
        return JSONResponse({"error": "Client storage unavailable — apply migration 007.",
                             "setup_required": True}, status_code=400)
    await write_audit(ws, _acc.get("email"), f"create_client:{created.get('id')}")
    return created


@app.get("/api/clients")
async def list_clients_endpoint(_acc: dict = Depends(require_role("member"))):
    from database import list_clients
    ws = await _acting_workspace(_acc)
    return {"clients": await list_clients(ws) if ws else []}


@app.post("/api/sites/{site_id}/assign-client")
async def assign_site_client_endpoint(site_id: str, client_id: str = Query(default=""),
                                      _acc: dict = Depends(require_site_access("member"))):
    from database import assign_site_client, write_audit
    await assign_site_client(site_id, client_id or None)
    await write_audit(_acc.get("workspace_id"), _acc.get("email"),
                      f"assign_site_client:{client_id or 'none'}", site_id)
    return {"status": "ok", "site_id": site_id, "client_id": client_id or None}


@app.post("/api/invites")
async def create_invite_endpoint(email: str = Query(...), client_id: str = Query(...),
                                 _acc: dict = Depends(require_role("member"))):
    """Create a client_viewer invite. Returns a shareable accept link (v1: the
    member shares it with the client; emailed magic-link re-login is v2)."""
    from datetime import datetime, timedelta, timezone
    from sharing import new_token
    from database import create_invite, write_audit
    ws = await _acting_workspace(_acc)
    if not ws:
        return JSONResponse({"error": "No workspace — run the backfill first.",
                             "setup_required": True}, status_code=400)
    token = new_token()
    expires = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    created = await create_invite(ws, client_id, email, "client_viewer", token, expires)
    if not created:
        return JSONResponse({"error": "Invite storage unavailable — apply migration 007.",
                             "setup_required": True}, status_code=400)
    await write_audit(ws, _acc.get("email"), f"invite:{email}")
    return {"token": token, "email": email,
            "accept_url": f"{_frontend_url()}/portal/accept?token={token}",
            "expires_at": expires}


@app.get("/api/invites")
async def list_invites_endpoint(_acc: dict = Depends(require_role("member"))):
    from database import list_invites
    ws = await _acting_workspace(_acc)
    return {"invites": await list_invites(ws) if ws else []}


@app.delete("/api/invites/{token}")
async def revoke_invite_endpoint(token: str, _acc: dict = Depends(require_role("member"))):
    from database import revoke_invite, write_audit
    ok = await revoke_invite(token)
    await write_audit(_acc.get("workspace_id"), _acc.get("email"), f"revoke_invite")
    return {"revoked": bool(ok)}


@app.post("/api/invites/{token}/accept")
async def accept_invite_endpoint(token: str):
    """PUBLIC — the invite token IS the credential. On success, mints the
    client's HS256 portal token (no NextAuth). Single-use + expiring."""
    from sharing import is_wellformed
    from database import accept_invite, write_audit
    from auth import mint_token, portal_enforced
    # Safety gate: with enforcement OFF the backend bypasses scoping, so a client
    # session would see every site. Refuse to mint one until the portal is armed.
    if not portal_enforced():
        return JSONResponse(
            {"error": "The client portal isn't live yet. Please check back soon."},
            status_code=503)
    if not is_wellformed(token):
        return JSONResponse({"error": "This invite link is invalid."}, status_code=404)
    result = await accept_invite(token, utcnow_iso())
    reason = result.get("reason") if result else "not_found"
    if reason:
        msg = {"not_found": "This invite link is invalid.",
               "revoked": "This invite has been revoked.",
               "used": "This invite has already been used.",
               "expired": "This invite has expired — ask for a new one.",
               "storage_unavailable": "Invites aren't set up yet — apply migration 007."}.get(reason, reason)
        return JSONResponse({"error": msg}, status_code=400 if reason != "not_found" else 404)
    portal_token = mint_token(result["email"], role=result.get("role"),
                              client_id=result.get("client_id"))
    await write_audit(result.get("workspace_id"), result["email"], "portal_login")
    return {"token": portal_token, "email": result["email"]}


@app.get("/api/audit")
async def audit_log_endpoint(_acc: dict = Depends(require_role("member"))):
    from database import list_audit
    ws = await _acting_workspace(_acc)
    return {"events": await list_audit(ws) if ws else []}


# ─── Client portal: per-client Resources (labeled links, QA cert, etc.) ──────
@app.post("/api/clients/{client_id}/resources")
async def add_resource_endpoint(client_id: str, title: str = Query(...), url: str = Query(...),
                                visible: bool = Query(default=True),
                                _acc: dict = Depends(require_role("member"))):
    from database import create_resource, write_audit
    ws = await _acting_workspace(_acc)
    created = await create_resource(client_id, ws, title.strip(), url.strip(), visible)
    if not created:
        return JSONResponse({"error": "Resource storage unavailable — apply migration 009.",
                             "setup_required": True}, status_code=400)
    await write_audit(ws, _acc.get("email"), f"add_resource:{client_id}")
    return created


@app.get("/api/clients/{client_id}/resources")
async def list_resources_endpoint(client_id: str, _acc: dict = Depends(require_role("member"))):
    from database import list_resources
    return {"resources": await list_resources(client_id, visible_only=False)}


@app.patch("/api/resources/{resource_id}")
async def update_resource_endpoint(resource_id: str, visible: bool = Query(...),
                                   _acc: dict = Depends(require_role("member"))):
    from database import set_resource_visible
    return {"ok": await set_resource_visible(resource_id, visible)}


@app.delete("/api/resources/{resource_id}")
async def delete_resource_endpoint(resource_id: str, _acc: dict = Depends(require_role("member"))):
    from database import delete_resource
    return {"deleted": await delete_resource(resource_id)}


@app.get("/api/portal/resources")
async def portal_resources_endpoint(request: Request):
    """The visible Resources for the calling client_viewer's client. Public route
    guarded by the portal token — resolves the caller's client from membership."""
    from auth import caller_email
    from database import any_membership, list_resources
    email = caller_email(request)
    if not email:
        return {"resources": []}
    m = await any_membership(email)
    if not m or m.get("role") != "client_viewer" or not m.get("client_id"):
        return {"resources": []}
    return {"resources": await list_resources(m["client_id"], visible_only=True)}


# ─── Wave 1: vigilance reports ───────────────────────────────────────────────
def _resolve_period(period: str):
    """period 'YYYY-MM' -> that calendar month; else the last 30 days."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    if period and len(period) == 7 and period[4] == "-":
        y, m = int(period[:4]), int(period[5:7])
        start = datetime(y, m, 1, tzinfo=timezone.utc)
        nm_y, nm_m = (y + 1, 1) if m == 12 else (y, m + 1)
        end = datetime(nm_y, nm_m, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
        return start, end, start.strftime("%B %Y")
    end = now
    start = now - timedelta(days=30)
    return start, end, end.strftime("%B %Y")


async def _report_slack(site_id, label: str, data: dict, report_id: str) -> None:
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook:
        return
    verdict = data.get("verdict", "")
    link = f"{_frontend_url()}/reports/{report_id}"
    text = f":page_facing_up: *Vigilance report ready — {label}*\n{verdict}\n<{link}|Open report>"
    try:
        async with httpx.AsyncClient() as client:
            await client.post(webhook, json={"text": text}, timeout=5.0)
    except Exception:
        pass


async def _build_report(site_id, period: str):
    from database import report_source, list_ad_destinations
    from vigilance_report import compute_report
    src = await report_source(site_id)
    start, end, label = _resolve_period(period)
    # Wave 2 hook: fold ad-destination protection into the report (honest — spend
    # only when cost was imported).
    ads = None
    try:
        dests = await list_ad_destinations(site_id)
        if dests:
            from ads_guard import summarize_guard
            g = summarize_guard(dests)
            ads = {"destinations_verified": g["total"], "incidents": g["broken"],
                   "has_cost": g["has_cost"], "spend_at_risk": g["spend"]["daily_at_risk"]}
    except Exception:
        ads = None
    data = compute_report(src["scans"], src["findings"], start, end,
                          forms_audited=src["forms_audited"],
                          integrations_watched=src["integrations_watched"], ads=ads)
    # Wave 3 hook: fill the uptime slot + a disasters-watched line from the sentinel.
    try:
        from database import get_sentinel_status, recent_pings, list_incidents
        from sentinel import uptime_pct as _uptime_pct
        pings = await recent_pings(site_id)
        up = _uptime_pct(pings)
        if up is not None:
            data["uptime_pct"] = up
        status = await get_sentinel_status(site_id)
        if status or up is not None:
            incidents = await list_incidents(site_id)
            in_period = [i for i in incidents if _in_report_period(i.get("down_at"), start, end)]
            data["disasters"] = {"watched": 4, "incidents": len(in_period)}
    except Exception:
        pass
    return start, end, label, data


def _in_report_period(iso, start, end):
    from datetime import datetime, timezone
    if not iso:
        return False
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        return start <= d <= end
    except Exception:
        return False


@app.get("/api/sites/{site_id}/report/preview")
async def report_preview(site_id: str, period: str = Query(default=""),
                         _acc: dict = Depends(require_site_access("member"))):
    _s, _e, label, data = await _build_report(site_id, period)
    return {"label": label, "data": data}


@app.post("/api/sites/{site_id}/report/generate")
async def report_generate(site_id: str, period: str = Query(default=""),
                          _acc: dict = Depends(require_site_access("member"))):
    from database import save_report
    start, end, label, data = await _build_report(site_id, period)
    saved = await save_report(site_id, start.isoformat(), end.isoformat(), label, data)
    if not saved:
        return JSONResponse({"error": "Report storage unavailable — apply migration 010.",
                             "setup_required": True}, status_code=400)
    await _report_slack(site_id, label, data, saved["id"])
    return {"id": saved["id"], "label": label, "data": data}


@app.get("/api/sites/{site_id}/reports")
async def report_list(site_id: str, _acc: dict = Depends(require_site_access("client_viewer"))):
    from database import list_reports
    return {"reports": await list_reports(site_id)}


@app.get("/api/reports/{report_id}")
async def report_get(report_id: str, request: Request):
    """A single report. Access-checked: agency member or the client_viewer whose
    client owns the report's site."""
    from auth import caller_email, portal_enforced
    from database import get_report, site_scope, resolve_membership
    report = await get_report(report_id)
    if not report:
        return JSONResponse({"error": "Report not found."}, status_code=404)
    if not portal_enforced():
        return report
    email = caller_email(request)
    if not email:
        return JSONResponse({"error": "Authentication required."}, status_code=401)
    scope = await site_scope(report["site_id"])
    m = await resolve_membership(email, scope["workspace_id"]) if scope and scope.get("workspace_id") else None
    if not m:
        return JSONResponse({"error": "No access."}, status_code=403)
    if m.get("role") == "client_viewer" and m.get("client_id") != (scope or {}).get("client_id"):
        return JSONResponse({"error": "Out of scope."}, status_code=403)
    return report


@app.get("/api/portal/reports")
async def portal_reports(request: Request):
    from auth import caller_email
    from database import any_membership, reports_for_client
    email = caller_email(request)
    if not email:
        return {"reports": []}
    m = await any_membership(email)
    if not m or m.get("role") != "client_viewer" or not m.get("client_id"):
        return {"reports": []}
    return {"reports": await reports_for_client(m["client_id"])}


# ─── Wave 2: Google Ads waste-guard ──────────────────────────────────────────
@app.post("/api/sites/{site_id}/ads/preview")
async def ads_preview(site_id: str, request: Request,
                      _acc: dict = Depends(require_site_access("member"))):
    """Parse an uploaded Ads export and return the parsed preview — no commit."""
    from ads_import import parse_ads_csv
    body = (await request.body()).decode("utf-8", "replace")
    return parse_ads_csv(body)


@app.post("/api/sites/{site_id}/ads/import")
async def ads_import_endpoint(site_id: str, request: Request,
                              _acc: dict = Depends(require_site_access("member"))):
    from ads_import import parse_ads_csv
    from database import replace_ad_destinations
    body = (await request.body()).decode("utf-8", "replace")
    parsed = parse_ads_csv(body)
    if not parsed["destinations"]:
        msg = parsed["warnings"][0] if parsed["warnings"] else "No ad destinations found in the file."
        return JSONResponse({"error": msg, "warnings": parsed["warnings"]}, status_code=400)
    res = await replace_ad_destinations(site_id, parsed["destinations"])
    if res.get("setup_required"):
        return JSONResponse({"error": "Ads storage unavailable — apply migration 011.",
                             "setup_required": True}, status_code=400)
    return {"imported": res["imported"], "campaigns": parsed["campaigns"],
            "has_cost": parsed["has_cost"], "skipped": parsed["skipped"]}


@app.get("/api/sites/{site_id}/ads")
async def ads_list(site_id: str, _acc: dict = Depends(require_site_access("client_viewer"))):
    from database import list_ad_destinations
    from ads_guard import summarize_guard
    return summarize_guard(await list_ad_destinations(site_id))


@app.post("/api/sites/{site_id}/ads/verify-now")
async def ads_verify_now(site_id: str, _acc: dict = Depends(require_site_access("member"))):
    """Verify every destination now (so the guard can be tested without waiting
    for the daily run). Same flap discipline, but on-demand."""
    from datetime import datetime, timezone
    from database import list_ad_destinations, update_ad_status
    from ads_guard import verify_ad, summarize_guard
    dests = await list_ad_destinations(site_id)
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        for d in dests:
            status, ms, _code = await verify_ad(d["final_url"], client=client)
            breach_since = d.get("breach_since")
            if status == "broken" and not breach_since:
                breach_since = datetime.now(timezone.utc).isoformat()
            elif status != "broken":
                breach_since = None
            await update_ad_status(d["id"], status, ms, breach_since)
    return summarize_guard(await list_ad_destinations(site_id))


@app.get("/api/portal/ads")
async def portal_ads(request: Request):
    from auth import caller_email
    from database import any_membership, ad_destinations_for_client
    from ads_guard import summarize_guard
    email = caller_email(request)
    if not email:
        return summarize_guard([])
    m = await any_membership(email)
    if not m or m.get("role") != "client_viewer" or not m.get("client_id"):
        return summarize_guard([])
    return summarize_guard(await ad_destinations_for_client(m["client_id"]))


# ─── Wave 3: Disaster Sentinel ───────────────────────────────────────────────
async def _sentinel_payload(site_id):
    from database import get_sentinel_status, recent_pings, list_incidents
    from sentinel import summarize_sentinel
    status = await get_sentinel_status(site_id)
    pings = await recent_pings(site_id)
    summary = summarize_sentinel(status, pings)
    summary["incidents"] = await list_incidents(site_id, limit=20)
    return summary


@app.get("/api/sites/{site_id}/sentinel")
async def sentinel_get(site_id: str, _acc: dict = Depends(require_site_access("client_viewer"))):
    return await _sentinel_payload(site_id)


@app.post("/api/sites/{site_id}/sentinel/check-now")
async def sentinel_check_now(site_id: str, _acc: dict = Depends(require_site_access("member"))):
    """Run the sentinel checks + one uptime ping now, so the guard can be tested
    without waiting for the daily/5-min schedule."""
    from database import get_site_url
    from sentinel import run_sentinel_for_site, run_uptime_for_site
    url = await get_site_url(site_id)
    site = {"id": site_id, "url": url}
    try:
        await run_sentinel_for_site(site, notify=_watchdog_slack)
        await run_uptime_for_site(site, notify=_watchdog_slack)
    except Exception as e:
        return JSONResponse({"error": f"Check failed: {e}"}, status_code=500)
    return await _sentinel_payload(site_id)


# ─── Verified Lead Delivery, Wave 1: form contracts ──────────────────────────
@app.post("/api/sites/{site_id}/contracts/draft")
async def contract_draft(site_id: str, request: Request,
                         _acc: dict = Depends(require_site_access("member"))):
    """Observe a form (hydrated render) and save a DRAFT contract for operator
    review. Never auto-confirmed."""
    from lead_contracts import (observe_page_forms, find_form, draft_from_observation,
                                hydrated_values_for, contract_key)
    from database import save_contract_version
    body = await request.json()
    page_url = (body.get("page_url") or "").strip()
    if not page_url:
        return JSONResponse({"error": "page_url is required."}, status_code=400)
    form_id = body.get("form_id") or ""
    index = body.get("index")
    try:
        observed = await observe_page_forms(page_url)
    except Exception as e:
        return JSONResponse({"error": f"Couldn't render the page to observe it: {e}"}, status_code=502)
    form = find_form(observed, form_id=form_id, index=index)
    if not form:
        return JSONResponse({"error": "No form found on that page to draft from."}, status_code=404)
    draft = draft_from_observation(form, page_url,
                                   hydrated_values=hydrated_values_for(form),
                                   scripts_text=observed.get("scripts_text", ""))
    key = contract_key(site_id, page_url, draft["form_ref"]["form_id"], draft["form_ref"]["selector"])
    saved = await save_contract_version(site_id, key, "draft", draft)
    if not saved:
        return JSONResponse({"error": "Contract storage unavailable — apply migration 013.",
                             "setup_required": True}, status_code=400)
    return {"contract": saved, "observed_fields": form.get("fields", [])}


@app.get("/api/sites/{site_id}/contracts")
async def contracts_list(site_id: str, _acc: dict = Depends(require_site_access("member"))):
    from database import list_contracts
    return {"contracts": await list_contracts(site_id)}


@app.post("/api/sites/{site_id}/contracts/{contract_key}/confirm")
async def contract_confirm(site_id: str, contract_key: str, request: Request,
                           _acc: dict = Depends(require_site_access("member"))):
    """Operator confirms (optionally edited) → a new immutable confirmed version."""
    from auth import caller_email
    from database import save_contract_version
    body = await request.json()
    draft = {"form_ref": body.get("form_ref", {}), "fields": body.get("fields", []),
             "destination": body.get("destination", {}), "events": body.get("events", [])}
    saved = await save_contract_version(site_id, contract_key, "confirmed", draft,
                                        confirmed_by=caller_email(request))
    if not saved:
        return JSONResponse({"error": "Contract storage unavailable — apply migration 013.",
                             "setup_required": True}, status_code=400)
    return {"contract": saved}


@app.post("/api/sites/{site_id}/contracts/drift-check")
async def contract_drift_check(site_id: str, request: Request,
                               _acc: dict = Depends(require_site_access("member"))):
    """Observe a page and validate every confirmed contract on it against reality.
    Returns per-contract violations (the drift surface)."""
    from lead_contracts import observe_page_forms, find_form, validate_drift, hydrated_values_for
    from database import confirmed_contracts
    body = await request.json()
    page_url = (body.get("page_url") or "").strip()
    if not page_url:
        return JSONResponse({"error": "page_url is required."}, status_code=400)
    try:
        observed = await observe_page_forms(page_url)
    except Exception as e:
        return JSONResponse({"error": f"Couldn't render the page: {e}"}, status_code=502)
    results = []
    for c in await confirmed_contracts(site_id):
        ref = c.get("form_ref") or {}
        if (ref.get("page_url") or "") != page_url:
            continue
        form = find_form(observed, form_id=ref.get("form_id") or "")
        if not form:
            results.append({"contract_id": c["id"], "form_ref": ref,
                            "violations": [{"kind": "field_removed", "field": "(whole form)",
                                            "severity": "critical",
                                            "consequence": "The whole form is gone from the page → no leads can be submitted."}]})
            continue
        violations = validate_drift(c, form, hydrated_values=hydrated_values_for(form),
                                    first_seen=c.get("confirmed_at"))
        results.append({"contract_id": c["id"], "form_ref": ref, "violations": violations})
    return {"results": results}


# ─── Verified Lead Delivery, Wave 2: the tracer ──────────────────────────────
async def _real_submit(*, url, selector, payload):
    """Real one-shot submitter — reuses the proven active-submission executor
    (payment refusal, honeypot-safe, exactly-once) in a thread."""
    import asyncio
    from active_submission_exec import submit_test_form
    email = next((v for k, v in payload.items() if "email" in k.lower()), None)
    res = await asyncio.to_thread(submit_test_form, url, selector, test_email=email)
    res = res or {}
    return {"submitted": bool(res.get("submitted")), "status": res.get("status"),
            "screenshot_ref": res.get("screenshot_ref") or res.get("screenshot")}


async def _current_confirmed_contract(site_id, contract_key):
    from database import confirmed_contracts
    for c in await confirmed_contracts(site_id):
        if c.get("contract_key") == contract_key:
            return c
    return None


async def execute_tracer_run(site_id, contract_key, mode="scheduled", run_token="run"):
    """Full run: gates → submit → verify → cleanup → ledger, with a single flap
    re-run before alerting, and Slack on any non-verified/cleanup-fail outcome."""
    from tracer import run_tracer, TracerRefused
    from database import get_enrollment, get_crm_connection, insert_tracer_run
    from crm_connectors import make_connector
    from tracer_crypto import decrypt, redact
    import json

    contract = await _current_confirmed_contract(site_id, contract_key)
    enrollment = await get_enrollment(site_id, contract_key)
    conn_row = await get_crm_connection(site_id)
    if not contract or not enrollment:
        return {"error": "No confirmed contract or enrollment for this form."}
    if not conn_row:
        return {"error": "Connect a CRM before running the tracer."}
    try:
        creds = json.loads(decrypt(conn_row["credentials_enc"]))
    except Exception:
        return {"error": "Stored CRM credentials could not be read."}
    connector = make_connector(conn_row["crm_type"], creds)

    async def _do():
        return await run_tracer(contract=contract, enrollment=enrollment, connector=connector,
                                submit_fn=_real_submit, mode=mode, run_token=run_token, max_polls=6)
    try:
        result = await _do()
        # Flap protection: one immediate re-run before we alert on a bad outcome.
        if result["needs_alert"] and result["alert_kind"] != "failed_cleanup":
            result = await _do()
    except TracerRefused as e:
        return {"refused": redact(str(e))}

    saved = await insert_tracer_run(result["row"])
    if result["needs_alert"]:
        kind = result["alert_kind"]
        loud = ":rotating_light:" if kind in ("failed_cleanup", "failed_arrival") else ":warning:"
        extra = ""
        if kind == "failed_cleanup" and result["row"].get("crm_contact_ref"):
            extra = f" — test contact {result['row']['crm_contact_ref']} NOT removed, delete manually"
        try:
            await _watchdog_slack(f"{loud} *Lead tracer: {kind}* on a monitored form{extra}")
        except Exception:
            pass
    return {"outcome": result["row"]["outcome"], "cleanup": result["row"]["cleanup"],
            "run_id": (saved or {}).get("id"), "mode": mode}


async def _run_tracer_sweep():
    """Daily job: run the tracer for every armed enrollment. Inert unless the
    flag is on. Small jitter so we don't hammer every CRM at once."""
    import asyncio
    from tracer import tracer_enabled
    from database import active_enrollments
    if not tracer_enabled():
        return {"skipped": "flag off"}
    n = 0
    for enr in await active_enrollments():
        try:
            await asyncio.sleep(min(30, n * 3))   # gentle jitter
            await execute_tracer_run(enr["site_id"], enr["contract_key"], mode="scheduled")
            n += 1
        except Exception:
            pass
    return {"ran": n}


@app.get("/api/sites/{site_id}/crm")
async def crm_status(site_id: str, _acc: dict = Depends(require_site_access("member"))):
    """Connection status only — NEVER the credentials."""
    from database import get_crm_connection
    row = await get_crm_connection(site_id)
    if not row:
        return {"connected": False}
    return {"connected": True, "crm_type": row["crm_type"], "test_ok": row.get("test_ok"),
            "test_detail": row.get("test_detail"), "last_tested_at": row.get("last_tested_at")}


@app.post("/api/sites/{site_id}/crm/connect")
async def crm_connect(site_id: str, request: Request,
                      _acc: dict = Depends(require_site_access("member"))):
    from crm_connectors import make_connector, CONNECT_GUIDANCE
    from tracer_crypto import encrypt
    from database import save_crm_connection
    import json
    body = await request.json()
    crm_type = (body.get("crm_type") or "").strip()
    creds = body.get("credentials") or {}
    if crm_type not in ("hubspot", "ghl"):
        return JSONResponse({"error": "Unsupported CRM."}, status_code=400)
    try:
        connector = make_connector(crm_type, creds)
        test = await connector.test_connection()
    except Exception:
        test = {"ok": False, "detail": "connection test failed"}
    enc = encrypt(json.dumps(creds))
    saved = await save_crm_connection(site_id, crm_type, enc, test.get("ok"), test.get("detail"))
    if not saved:
        return JSONResponse({"error": "CRM storage unavailable — apply migration 014.",
                             "setup_required": True}, status_code=400)
    return {"test_ok": test.get("ok"), "detail": test.get("detail"),
            "guidance": CONNECT_GUIDANCE.get(crm_type)}


@app.post("/api/sites/{site_id}/tracer/enroll")
async def tracer_enroll(site_id: str, request: Request,
                        _acc: dict = Depends(require_site_access("member"))):
    from auth import caller_email
    from database import save_enrollment
    from tracer import default_test_email
    from datetime import datetime, timezone
    body = await request.json()
    if not body.get("acknowledged"):
        return JSONResponse({"error": "You must acknowledge that the test pattern is "
                             "excluded from automations before enrolling."}, status_code=400)
    contract_key = body.get("contract_key")
    patch = {
        "enabled": True, "acknowledged": True, "acknowledged_by": caller_email(request),
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        "test_email": body.get("test_email") or default_test_email(),
        "marker_field": body.get("marker_field"),
        "dry_run_passed": False, "schedule_active": False,
    }
    saved = await save_enrollment(site_id, contract_key, patch)
    if not saved:
        return JSONResponse({"error": "Enrollment storage unavailable — apply migration 014.",
                             "setup_required": True}, status_code=400)
    return {"enrollment": saved}


@app.post("/api/sites/{site_id}/tracer/run-now")
async def tracer_run_now(site_id: str, request: Request,
                         _acc: dict = Depends(require_site_access("member"))):
    """Manual run. First run after enrollment is a DRY-RUN setup validation; the
    daily schedule stays off until it passes and the operator activates."""
    from tracer import tracer_enabled
    from database import get_enrollment, save_enrollment
    if not tracer_enabled():
        return JSONResponse({"error": "TRACER_ENABLED is off — arm it before running.",
                             "flag_off": True}, status_code=400)
    body = await request.json()
    contract_key = body.get("contract_key")
    enr = await get_enrollment(site_id, contract_key)
    if not enr:
        return JSONResponse({"error": "This form is not enrolled."}, status_code=400)
    mode = "dryrun" if not enr.get("dry_run_passed") else "manual"
    res = await execute_tracer_run(site_id, contract_key, mode=mode)
    if mode == "dryrun" and res.get("outcome") == "verified":
        await save_enrollment(site_id, contract_key, {"dry_run_passed": True})
        res["dry_run_passed"] = True
    return res


@app.post("/api/sites/{site_id}/tracer/activate")
async def tracer_activate(site_id: str, request: Request,
                          _acc: dict = Depends(require_site_access("member"))):
    """Operator confirms setup validation → arm the daily schedule for this form."""
    from database import get_enrollment, save_enrollment
    body = await request.json()
    contract_key = body.get("contract_key")
    enr = await get_enrollment(site_id, contract_key)
    if not enr or not enr.get("dry_run_passed"):
        return JSONResponse({"error": "Run a passing dry-run first."}, status_code=400)
    saved = await save_enrollment(site_id, contract_key, {"schedule_active": True})
    return {"enrollment": saved}


@app.get("/api/sites/{site_id}/tracer/stamp")
async def tracer_stamp(site_id: str, _acc: dict = Depends(require_site_access("client_viewer"))):
    from database import runs_for_site
    from tracer import stamp_summary
    return stamp_summary(await runs_for_site(site_id))


@app.get("/api/sites/{site_id}/tracer/runs")
async def tracer_runs(site_id: str, _acc: dict = Depends(require_site_access("client_viewer"))):
    from database import runs_for_site
    return {"runs": await runs_for_site(site_id)}


# ─── Insight Layer, PR1: the Intent Map ──────────────────────────────────────
@app.get("/api/sites/{site_id}/intent-map")
async def intent_map_endpoint(site_id: str, _acc: dict = Depends(require_site_access("client_viewer"))):
    """Every money-promise the site makes, and whether it's honored. Read-only
    join over the latest scan's links + integrations + form signals."""
    from database import latest_scan_for_site, get_integrations
    from intent_map import compute_intent_map
    scan = await latest_scan_for_site(site_id)
    if not scan:
        return {"verdict": "No scan yet — run a scan to map this site's promises.",
                "all_clear": False, "counts": {"conversion_total": 0, "honored": 0, "broken": 0,
                "unverified": 0, "functional_total": 0}, "promises": [], "no_scan": True}
    links = scan.get("results_json") or []
    integrations = await get_integrations(scan["id"]) or []
    cats = {i.get("category") for i in integrations if i.get("category")}
    chat_healthy = None
    for i in integrations:
        if i.get("category") == "Chat/Support":
            chat_healthy = i.get("health") in ("healthy", None)
            break
    has_form = any((r.get("resource_type") if isinstance(r, dict) else None) == "form_action" for r in links) \
        or "CRM/Forms" in cats
    return compute_intent_map(links, integration_categories=cats,
                              chat_healthy=chat_healthy, has_site_form=has_form)


# ─── Insight Layer PR2: Performance Regression Ledger ────────────────────────
async def _recompute_perf_all():
    """Nightly: refresh perf snapshots for every site (cheap — only new scans)."""
    from database import all_sites_min
    for s in await all_sites_min():
        try:
            await _recompute_perf(s["id"])
        except Exception:
            pass
    return {"ok": True}


async def _recompute_perf(site_id):
    """Backfill/refresh perf_snapshots from scans.results_json — recomputable
    from source at any time. Only computes scans not already cached."""
    from database import (scans_min_for_site, perf_series, scan_results, upsert_perf_snapshot)
    from perf_ledger import aggregate_scan
    scans = await scans_min_for_site(site_id)
    have = {s["scan_id"] for s in await perf_series(site_id)}
    for s in scans:
        if s["id"] in have:
            continue
        results = await scan_results(s["id"])
        agg = aggregate_scan(results)
        await upsert_perf_snapshot({
            "scan_id": s["id"], "site_id": site_id, "scanned_at": s["scanned_at"],
            "p50": agg["p50"], "p90": agg["p90"], "sample_count": agg["n"],
            "resource_count": len(results or []),
        })


async def _suspects_for_window(series, reg):
    """What changed between the scan before the regression and its first scan."""
    from database import get_integrations
    from perf_ledger import correlate_suspects, suspect_language
    idx = next((i for i, p in enumerate(series) if p.get("scanned_at") == reg["start_at"]), None)
    if idx is None or idx == 0:
        return {"suspects": [], "language": suspect_language([])}
    before_scan, after_scan = series[idx - 1], series[idx]

    async def sig(row):
        ints = await get_integrations(row["scan_id"]) or []
        return {"integrations": {(i.get("host") or i.get("category")) for i in ints if (i.get("host") or i.get("category"))},
                "resource_count": row.get("resource_count") or 0, "redirect_hops": 0}
    suspects = correlate_suspects(await sig(before_scan), await sig(after_scan))
    return {"suspects": suspects, "language": suspect_language(suspects)}


@app.get("/api/sites/{site_id}/performance")
async def performance_ledger(site_id: str, _acc: dict = Depends(require_site_access("client_viewer"))):
    from database import perf_series
    from perf_ledger import detect_regressions, build_verdict
    await _recompute_perf(site_id)
    series = await perf_series(site_id)
    regs = detect_regressions(series)
    for r in regs:
        r["window"] = await _suspects_for_window(series, r)
    verdict = build_verdict(series, regs)
    # Name the suspect in the verdict when a single ongoing regression has one.
    if verdict.get("state") == "slower" and verdict.get("regression"):
        w = verdict["regression"].get("window") or {}
        lang = w.get("language") or {}
        if lang.get("confidence") == "likely":
            verdict["text"] = verdict["text"].rstrip(".") + f" — {lang['text']}."
    return {"verdict": verdict, "regressions": regs,
            "series": [{"scanned_at": p["scanned_at"], "p50": p["p50"], "p90": p["p90"]} for p in series]}


@app.get("/api/performance/cost-index")
async def performance_cost_index(request: Request, _acc: dict = Depends(require_role("member"))):
    """Third-party latency cost across the whole portfolio — needs the multi-site
    vantage. Observational: per host, median site-p50 where present minus the
    portfolio median where absent."""
    from database import all_perf_snapshots, perf_series, get_integrations
    from statistics import median
    snaps = await all_perf_snapshots()
    sites = sorted({s["site_id"] for s in snaps})
    # latest p50 + integration hosts per site
    site_p50, host_sites = {}, {}
    for sid in sites:
        ser = await perf_series(sid)
        if not ser or ser[-1].get("p50") is None:
            continue
        site_p50[sid] = ser[-1]["p50"]
        ints = await get_integrations(ser[-1]["scan_id"]) or []
        for h in {(i.get("host") or i.get("category")) for i in ints if (i.get("host") or i.get("category"))}:
            host_sites.setdefault(h, set()).add(sid)
    all_p50 = list(site_p50.values())
    baseline = median(all_p50) if all_p50 else 0
    index = []
    for host, ss in host_sites.items():
        present = [site_p50[s] for s in ss if s in site_p50]
        if len(present) < 2:
            continue
        index.append({"host": host, "sites": len(present),
                      "median_added_ms": round(median(present) - baseline)})
    index = [x for x in index if x["median_added_ms"] > 0]
    index.sort(key=lambda x: -x["median_added_ms"])
    return {"portfolio_baseline_p50": round(baseline), "index": index,
            "method": "Observational: median load on sites where the host is present, minus the portfolio median. Not a controlled measurement."}


@app.get("/health")
async def health():
    return {"status": "ok"}
