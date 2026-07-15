"""The one Postgres-backed jobs queue (ARCHITECTURE.md v7 §3).

ONE enqueue() function is the only way a row enters `jobs`. Claim/complete/fail
go through SQL functions (jobs_claim / jobs_complete / jobs_fail) so the atomic
`FOR UPDATE SKIP LOCKED` claim runs inside Postgres — the LinkSpy backend speaks
to Supabase via PostgREST, not raw SQL, so app-side row locking isn't available
(and the RPC is cleaner anyway; see docs/design-notes/gate-0b-jobs-foundation.md).

One asyncio worker drains the queue inside the always-on Railway process. The
whole thing is gated behind JOBS_SHADOW so deploying this changes NOTHING until
migration 021 is applied and the flag is flipped on.
"""
import asyncio
import os
import socket
from datetime import datetime, timezone

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
LEASE_SECONDS = int(os.getenv("JOBS_LEASE_SECONDS", "60"))
POLL_IDLE = float(os.getenv("JOBS_POLL_SECONDS", "2"))

# kind -> async handler(payload). Registered via @handler("kind").
_HANDLERS = {}


def handler(kind):
    def deco(fn):
        _HANDLERS[kind] = fn
        return fn
    return deco


def registered_kinds():
    return sorted(_HANDLERS)


# ── the ONE inserter (idempotent per (kind, idempotency_key)) ────────────────
def _enqueue_sync(kind, payload, idempotency_key, max_attempts, run_after):
    from database import _get_client, _tables_missing
    client = _get_client()
    row = {"kind": kind, "payload": payload or {}, "idempotency_key": idempotency_key,
           "max_attempts": int(max_attempts), "status": "queued"}
    if run_after:
        row["run_after"] = run_after
    try:
        # ON CONFLICT (kind, idempotency_key) DO NOTHING → duplicate = no-op.
        r = client.table("jobs").upsert(
            row, on_conflict="kind,idempotency_key", ignore_duplicates=True).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def enqueue(kind, payload=None, *, idempotency_key, max_attempts=5, run_after=None):
    """The single entry point into `jobs`. Every producer uses this — nothing
    else may INSERT into the table (enforced by tests/test_jobs_single_writer)."""
    return await asyncio.to_thread(_enqueue_sync, kind, payload, idempotency_key, max_attempts, run_after)


# ── claim / complete / fail via RPC ──────────────────────────────────────────
def _rpc_sync(fn, params):
    from database import _get_client
    r = _get_client().rpc(fn, params).execute()
    data = r.data or []
    return data[0] if data else None


async def claim(kinds=None):
    return await asyncio.to_thread(
        _rpc_sync, "jobs_claim",
        {"p_worker": WORKER_ID, "p_lease_seconds": LEASE_SECONDS, "p_kinds": kinds})


async def complete(job_id):
    return await asyncio.to_thread(_rpc_sync, "jobs_complete", {"p_id": job_id})


async def fail(job_id, error):
    return await asyncio.to_thread(_rpc_sync, "jobs_fail", {"p_id": job_id, "p_error": str(error)[:2000]})


# ── the worker loop ──────────────────────────────────────────────────────────
async def _dispatch(job):
    fn = _HANDLERS.get(job.get("kind"))
    if not fn:
        await fail(job["id"], f"no handler registered for kind={job.get('kind')}")
        return
    try:
        await fn(job.get("payload") or {})
        await complete(job["id"])
    except Exception as e:
        await fail(job["id"], repr(e))


async def run_worker(kinds=None, stop_event=None):
    """Drain loop. One per process; the claim is concurrency-safe so more can be
    added later with zero changes. Never raises out of the loop."""
    print(f"[jobs] worker {WORKER_ID} started (kinds={kinds or 'any'}, lease={LEASE_SECONDS}s)")
    while not (stop_event and stop_event.is_set()):
        try:
            job = await claim(kinds)
        except Exception as e:
            print(f"[jobs] claim error: {e!r}")
            await asyncio.sleep(POLL_IDLE)
            continue
        if not job:
            await asyncio.sleep(POLL_IDLE)
            continue
        await _dispatch(job)


# ── read-only stats for the admin endpoint ───────────────────────────────────
def _stats_sync():
    from database import _get_client, _tables_missing
    client = _get_client()
    try:
        def count(status):
            return client.table("jobs").select("id", count="exact").eq("status", status).execute().count or 0
        oldest = client.table("jobs").select("created_at").eq("status", "queued")\
            .order("created_at").limit(1).execute().data or []
        oldest_age_s = None
        if oldest:
            d = datetime.fromisoformat(str(oldest[0]["created_at"]).replace("Z", "+00:00"))
            oldest_age_s = int((datetime.now(timezone.utc) - d).total_seconds())
        recent_fail = client.table("jobs").select("id, kind, last_error, finished_at")\
            .in_("status", ["failed", "dead"]).order("finished_at", desc=True).limit(10).execute().data or []
        return {"queued": count("queued"), "running": count("running"), "done": count("done"),
                "failed": count("failed"), "dead": count("dead"),
                "oldest_queued_age_s": oldest_age_s, "recent_failures": recent_fail}
    except Exception as e:
        if _tables_missing(e):
            return {"unavailable": True, "reason": "jobs table not migrated yet (apply migration 021)"}
        raise


async def stats():
    return await asyncio.to_thread(_stats_sync)


# ── shadow handler: monitoring scans run as no-ops until the live flip ────────
def monitoring_is_live():
    return os.getenv("JOBS_MONITORING_LIVE") == "1"


@handler("monitoring_scan")
async def _monitoring_scan(payload):
    if not monitoring_is_live():
        # SHADOW / dry-run: prove claim+lease+retry at real cadence, scan nothing.
        print(f"[jobs:shadow] would scan site={payload.get('site_id')} "
              f"url={payload.get('url')} — dry-run, no scan performed")
        return
    # Live path is intentionally NOT enabled in Gate 0B (do not flip).
    raise RuntimeError("monitoring_scan live path is not enabled yet (shadow only)")


async def shadow_enqueue_monitoring():
    """Enqueue one dry-run monitoring_scan per monitored site, idempotent within
    the hour bucket. Called on an interval only when JOBS_SHADOW=1; the legacy
    scheduler keeps scanning for real in parallel."""
    if os.getenv("JOBS_SHADOW") != "1":
        return 0
    from database import get_monitored_sites
    sites = await get_monitored_sites()
    bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    n = 0
    for s in sites:
        try:
            await enqueue("monitoring_scan", {"site_id": s.get("id"), "url": s.get("url")},
                          idempotency_key=f"{s.get('id')}:{bucket}")
            n += 1
        except Exception as e:
            print(f"[jobs:shadow] enqueue failed for {s.get('id')}: {e!r}")
    return n
