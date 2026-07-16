"""Spine (Phase 2C, LinkSpy) — the qa_battery job handler plus the heartbeat_watch
and reconcile routines. Imported by main at startup so @handler registration
happens before the worker runs. Reuses the EXISTING qa-bridge check catalog; no
new probes. Machine results are written ONLY to qa_prefills (never a QA table).
"""
import os
from datetime import datetime, timezone, timedelta

import httpx

from jobs import handler


async def _slack(text: str) -> None:
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(webhook, json={"text": text}, timeout=5.0)
    except Exception:
        pass


def _age_seconds(iso) -> float:
    if not iso:
        return 1e12
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).total_seconds()
    except Exception:
        return 1e12


# ── qa.completed → monitoring auto-enroll (Part A) ──
def should_auto_enroll(flag_on: bool, monitoring_enabled) -> bool:
    """Enroll only when the flag is on AND the site is currently unmonitored.
    Never downgrades an existing cadence (monitored → skip)."""
    return bool(flag_on) and not bool(monitoring_enabled)


async def maybe_auto_enroll(registry_site_id, registry_deliverable_id):
    """On qa.completed: enroll an UNMONITORED site into weekly monitoring. Gated
    by AUTO_ENROLL (default off = no-op). Idempotent by state (once enabled, later
    events skip). Never touches a site that is already monitored."""
    if not (os.getenv("AUTO_ENROLL") == "1" and registry_site_id):
        return {"enrolled": False}
    from database import get_site, set_monitoring, timeline_add
    site = await get_site(registry_site_id)
    if not site or not should_auto_enroll(True, site.get("monitoring_enabled")):
        return {"enrolled": False}
    await set_monitoring(registry_site_id, True, "Weekly")
    await timeline_add(registry_site_id, registry_deliverable_id, "monitoring.auto_enrolled",
                       {"cadence": "Weekly"}, source="auto_enroll")
    frontend = os.getenv("FRONTEND_URL")
    link = f"{frontend.rstrip('/')}/dashboard/{registry_site_id}" if frontend else "(revert in the dashboard)"
    await _slack(f":satellite: auto-enrolled {site.get('url') or registry_site_id} to weekly "
                 f"monitoring after QA sign-off — one-click revert: {link}")
    return {"enrolled": True}


# ── the battery: run the existing catalog, write pre-fills ──
@handler("qa_battery")
async def qa_battery(payload):
    from database import registry_deliverable_by_id, prefills_write, qa_snapshot
    from qa_catalog import derive_checks
    deliverable_id = (payload or {}).get("deliverable_id")
    if not deliverable_id:
        return
    d = await registry_deliverable_by_id(deliverable_id)
    if not d:
        return
    snap = await qa_snapshot(d["site_id"], d.get("url"))
    checks = derive_checks(snap)
    run_at = datetime.now(timezone.utc).isoformat()
    await prefills_write(
        deliverable_id,
        [{"key": c["key"], "verdict": c["verdict"], "detail_plain": c.get("detail_plain"),
          "evidence_ref": c.get("source")} for c in checks],
        run_at,
    )


# ── heartbeat watch: alert once per silence if no heartbeat in >2h ──
@handler("heartbeat_watch")
async def heartbeat_watch(payload=None):
    from database import spine_marker_get, spine_marker_set
    hb = await spine_marker_get("heartbeat")
    age = _age_seconds(hb)
    if age > 2 * 3600:
        alerted = await spine_marker_get("heartbeat_alerted")
        # alert once per silence: only if we haven't alerted since the last heartbeat
        if not alerted or _age_seconds(alerted) > age:
            await _slack(":warning: *Spine heartbeat silent* — no event from the QA outbox in "
                         f"{int(age // 3600)}h. Check the Vercel drain cron / SPINE_EMIT.")
            await spine_marker_set("heartbeat_alerted")
    return {"age_seconds": age}


# ── reconcile (nightly, DETECT + ALERT only; auto-replay deferred) ──
@handler("reconcile")
async def reconcile(payload=None):
    from database import _get_client
    import asyncio
    client = _get_client()
    problems = []

    # Inbox side: received-not-processed for > 1h.
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        stuck = client.table("spine_inbox").select("id, type, received_at")\
            .eq("status", "received").lt("received_at", cutoff).limit(50).execute().data or []
        if stuck:
            problems.append(f"{len(stuck)} inbox event(s) received but unprocessed >1h")
    except Exception:
        pass

    # Outbox side (best-effort): ask the QA app for undelivered counts per mapped
    # deliverable. Needs QA_APP_URL + SPINE_SECRET; skipped otherwise.
    qa_url = os.getenv("QA_APP_URL")
    secret = os.getenv("SPINE_SECRET")
    if qa_url and secret:
        try:
            def _ids():
                return [d["id"] for d in (client.table("deliverables").select("id")
                        .not_.is_("external_ref", "null").limit(500).execute().data or [])]
            ids = await asyncio.to_thread(_ids)
            if ids:
                async with httpx.AsyncClient() as h:
                    r = await h.get(f"{qa_url.rstrip('/')}/api/spine/outbox-status",
                                    params={"ids": ",".join(ids)},
                                    headers={"Authorization": f"Bearer {secret}"}, timeout=10.0)
                if r.status_code == 200:
                    status = (r.json() or {}).get("status", {})
                    undelivered = sum(1 for v in status.values() if (v or {}).get("undelivered", 0) > 0)
                    if undelivered:
                        problems.append(f"{undelivered} deliverable(s) with undelivered outbox rows")
        except Exception:
            pass

    if problems:
        await _slack(":mag: *Spine reconcile* found drift:\n• " + "\n• ".join(problems)
                     + "\n(v1: detect + alert; no auto-replay.)")
    return {"problems": problems}
