import os
import threading
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def _get_client():
    from supabase import create_client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("supabase_url is required")
    return create_client(url, key)


def _save_scan_sync(site_url, user_email, results, health_score, pages_scanned=1):
    client = _get_client()
    
    def get_val(r, key):
        return r.get(key) if isinstance(r, dict) else getattr(r, key, None)
    
    total = len(results)
    broken = sum(1 for r in results if get_val(r, "label") == "broken")
    dead_cta = sum(1 for r in results if get_val(r, "label") == "dead_cta")
    redirect = sum(1 for r in results if get_val(r, "label") == "redirect")
    blocked = sum(1 for r in results if get_val(r, "label") == "blocked")

    # Insert site
    site_resp = client.table("sites").upsert({
        "url": site_url,
        "user_email": user_email,
        "last_scanned_at": "now()",
    }, on_conflict="url,user_email").execute()

    site_id = site_resp.data[0]["id"]

    # Save scan
    scan_payload = {
        "site_id": site_id,
        "total_links": total,
        "broken_count": broken,
        "dead_cta_count": dead_cta,
        "redirect_count": redirect,
        "blocked_count": blocked,
        "health_score": health_score,
        "results_json": [r if isinstance(r, dict) else r.dict() for r in results],
        # Optional: older deployments have no such column. See _insert_scan.
        "pages_scanned": pages_scanned,
    }

    scan_resp = _insert_scan(client, scan_payload)
    scan_id = scan_resp.data[0]["id"]

    # Issue tracking is a bonus. It must never cost us the scan row, which is
    # what the History panel reads.
    try:
        _track_issues(client, site_id, scan_id, results, get_val)
    except Exception as e:
        print(f"[DB] issue tracking failed (scan {scan_id} was still saved): {e}")

    print(f"[DB] Saved scan for {site_url} — {total} links, score {health_score}")
    return {"site_id": site_id, "scan_id": scan_id}


# Columns that some deployments' `scans` table predates. Inserting one the
# schema does not have makes PostgREST reject the whole row — which used to
# throw away every scan, silently, leaving the History panel permanently empty.
_OPTIONAL_SCAN_COLUMNS = ("pages_scanned",)


def _insert_scan(client, payload: dict):
    try:
        return client.table("scans").insert(payload).execute()
    except Exception as e:
        trimmed = {k: v for k, v in payload.items() if k not in _OPTIONAL_SCAN_COLUMNS}
        if trimmed == payload:
            raise   # nothing optional to drop — a real failure
        print(f"[DB] scans insert failed ({e}); retrying without {_OPTIONAL_SCAN_COLUMNS}")
        return client.table("scans").insert(trimmed).execute()


def _track_issues(client, site_id, scan_id, results, get_val):
    for r in results:
        label = get_val(r, "label")
        r_url = get_val(r, "url")
        if label in ["broken", "dead_cta", "error"]:
            # Check if already exists
            existing = client.table("link_issues")\
                .select("id")\
                .eq("site_id", site_id)\
                .eq("url", r_url)\
                .is_("resolved_at", "null")\
                .execute()

            if existing.data:
                # Update last_seen
                client.table("link_issues")\
                    .update({"last_seen_at": "now()", "is_new": False})\
                    .eq("id", existing.data[0]["id"])\
                    .execute()
            else:
                # New issue
                client.table("link_issues").insert({
                    "site_id": site_id,
                    "scan_id": scan_id,
                    "url": r_url,
                    "label": label,
                    "category": get_val(r, "category"),
                    "anchor_text": get_val(r, "anchor_text"),
                    "status_code": get_val(r, "status_code"),
                    "is_new": True,
                }).execute()

    # Mark resolved issues
    all_current_broken = {
        get_val(r, "url") for r in results
        if get_val(r, "label") in ["broken", "dead_cta", "error"]
    }
    open_issues = client.table("link_issues")\
        .select("id, url")\
        .eq("site_id", site_id)\
        .is_("resolved_at", "null")\
        .execute()

    for issue in open_issues.data:
        if issue["url"] not in all_current_broken:
            client.table("link_issues")\
                .update({"resolved_at": "now()"})\
                .eq("id", issue["id"])\
                .execute()


def save_scan_threaded(site_url, user_email, results, health_score, pages_scanned=1):
    """Run in a completely separate thread — no asyncio involvement."""
    result_container = {}
    error_container = {}

    def run():
        try:
            result_container["data"] = _save_scan_sync(
                site_url, user_email, results, health_score, pages_scanned
            )
        except Exception as e:
            error_container["err"] = e
            print(f"[DB] Save failed: {e}")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=15)  # wait max 15 seconds

    if "err" in error_container:
        raise error_container["err"]
    return result_container.get("data", {})


async def save_scan(site_url, user_email, results, health_score, pages_scanned=1):
    """Async wrapper that runs DB save in a real thread."""
    import asyncio
    return await asyncio.to_thread(
        save_scan_threaded, site_url, user_email, results, health_score, pages_scanned
    )


def _get_uptime_sync(site_url: str) -> list:
    client = _get_client()

    resp = client.table("link_issues")\
        .select("url, label, category, anchor_text, first_seen_at, last_seen_at, is_new, sites!inner(url)")\
        .eq("sites.url", site_url)\
        .is_("resolved_at", "null")\
        .order("first_seen_at", desc=False)\
        .execute()

    return resp.data


async def get_uptime(site_url: str) -> list:
    import asyncio
    return await asyncio.to_thread(_get_uptime_sync, site_url)

async def get_site_history(site_url, user_email):
    def _get():
        client = _get_client()
        resp = client.table("scans")\
            .select("*, sites!inner(url, user_email)")\
            .eq("sites.url", site_url)\
            .eq("sites.user_email", user_email)\
            .order("scanned_at", desc=True)\
            .limit(30)\
            .execute()
        return resp.data
    import asyncio
    return await asyncio.to_thread(_get)


def _add_site_sync(url: str, name: str, client_name: str, freq: str, user_email: str):
    client = _get_client()
    # upsert the site. We ignore errors if columns don't exist yet via try/except if needed,
    # but the user will run the SQL to add the columns.
    resp = client.table("sites").upsert({
        "url": url,
        "name": name,
        "client": client_name,
        "freq": freq,
        "user_email": user_email,
        # last_scanned_at will be null initially for a new site, or omitted so it takes default
    }, on_conflict="url,user_email").execute()
    return resp.data

async def add_site(url: str, name: str, client_name: str, freq: str, user_email: str):
    import asyncio
    return await asyncio.to_thread(_add_site_sync, url, name, client_name, freq, user_email)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: baseline diffing (scan_snapshots + findings)
#
# These raise on failure. They used to swallow every exception and return a
# neutral value, which made "the tables do not exist" indistinguishable from
# "this site has no previous snapshot" — so a project that never ran
# migrations/001 was told "No previous scan to compare against" forever, on
# every scan, with the real error buried in a server log.
#
# Every caller already wraps these, and a failure still never takes a scan down.
# It is now *reported* rather than hidden: the scan returns
# baseline_status="unavailable" instead of pretending it is the first scan.
# ─────────────────────────────────────────────────────────────────────────────
def _latest_snapshot_sync(site_id: str) -> Optional[dict]:
    client = _get_client()
    resp = client.table("scan_snapshots")\
        .select("id, created_at, totals_json")\
        .eq("site_id", site_id)\
        .order("created_at", desc=True)\
        .limit(1)\
        .execute()
    return resp.data[0] if resp.data else None


def _findings_for_snapshot_sync(snapshot_id: str) -> list:
    client = _get_client()
    resp = client.table("findings")\
        .select("fingerprint, bucket, confidence, url, anchor_text, zone, "
                "reason, first_seen_at, resolved_at, status")\
        .eq("snapshot_id", snapshot_id)\
        .execute()
    return resp.data or []


def _save_snapshot_sync(site_id, scan_id, totals, findings, resolved) -> Optional[str]:
    client = _get_client()

    snap = client.table("scan_snapshots").insert({
        "site_id": site_id,
        "scan_id": scan_id,
        "totals_json": totals,
    }).execute()
    snapshot_id = snap.data[0]["id"]

    if findings:
        client.table("findings").insert([
            {**f, "snapshot_id": snapshot_id, "site_id": site_id} for f in findings
        ]).execute()

    # Stamp findings that disappeared this scan. They live on their previous
    # snapshot's rows, which is what the diff endpoint reads back.
    for fp, resolved_at in resolved:
        client.table("findings")\
            .update({"resolved_at": resolved_at, "status": "resolved"})\
            .eq("site_id", site_id)\
            .eq("fingerprint", fp)\
            .is_("resolved_at", "null")\
            .execute()

    return snapshot_id


def _recent_snapshots_sync(site_id: str, limit: int) -> list:
    client = _get_client()
    resp = client.table("scan_snapshots")\
        .select("id, created_at, totals_json")\
        .eq("site_id", site_id)\
        .order("created_at", desc=True)\
        .limit(limit)\
        .execute()
    return resp.data or []


async def get_recent_snapshots(site_id: str, limit: int = 2) -> list:
    """Newest first. The diff endpoint compares [0] against [1]. Raises on failure."""
    import asyncio
    return await asyncio.to_thread(_recent_snapshots_sync, site_id, limit)


async def get_latest_snapshot(site_id: str) -> Optional[dict]:
    """None means the site has no snapshot yet. Raises if the lookup failed."""
    import asyncio
    return await asyncio.to_thread(_latest_snapshot_sync, site_id)


async def get_findings_for_snapshot(snapshot_id: str) -> list:
    import asyncio
    return await asyncio.to_thread(_findings_for_snapshot_sync, snapshot_id)


async def save_snapshot(site_id, scan_id, totals, findings, resolved) -> Optional[str]:
    import asyncio
    return await asyncio.to_thread(
        _save_snapshot_sync, site_id, scan_id, totals, findings, resolved
    )


def _site_id_for_url_sync(site_url: str, user_email: str) -> Optional[str]:
    client = _get_client()
    resp = client.table("sites").select("id")\
        .eq("url", site_url).eq("user_email", user_email).limit(1).execute()
    return resp.data[0]["id"] if resp.data else None


async def get_site_id(site_url: str, user_email: str) -> Optional[str]:
    """None means the site has never been scanned. Raises if the lookup failed."""
    import asyncio
    return await asyncio.to_thread(_site_id_for_url_sync, site_url, user_email)


def _diffing_tables_ready_sync() -> dict:
    """Probe the Phase 1 tables. A valid-but-absent id returns [] when the table
    exists, and raises when it does not."""
    client = _get_client()
    probe_id = "00000000-0000-0000-0000-000000000000"
    checks = {}
    for table, column in (("scan_snapshots", "site_id"), ("findings", "snapshot_id")):
        try:
            client.table(table).select("id").eq(column, probe_id).limit(1).execute()
            checks[table] = "ok"
        except Exception as e:
            checks[table] = f"error: {type(e).__name__}: {str(e)[:200]}"
    return checks


async def diffing_tables_ready() -> dict:
    import asyncio
    return await asyncio.to_thread(_diffing_tables_ready_sync)


def _site_storage_report_sync(site_url: str, user_email: str) -> dict:
    """How much of this site actually made it into storage.

    Answers, in one request, both "why is History empty" (no scans rows) and
    "why is there no baseline" (no scan_snapshots rows).
    """
    client = _get_client()

    def count(table: str, column: str, value) -> object:
        try:
            resp = client.table(table).select("id", count="exact")\
                .eq(column, value).limit(1).execute()
            return resp.count
        except Exception as e:
            return f"error: {type(e).__name__}: {str(e)[:120]}"

    site = client.table("sites").select("id")\
        .eq("url", site_url).eq("user_email", user_email).limit(1).execute()
    if not site.data:
        return {"site_found": False, "site_url": site_url, "user_email": user_email}

    site_id = site.data[0]["id"]
    return {
        "site_found": True,
        "site_id": site_id,
        "scans": count("scans", "site_id", site_id),
        "scan_snapshots": count("scan_snapshots", "site_id", site_id),
        "findings": count("findings", "site_id", site_id),
    }


async def site_storage_report(site_url: str, user_email: str) -> dict:
    import asyncio
    return await asyncio.to_thread(_site_storage_report_sync, site_url, user_email)


def _delete_site_sync(site_id: str):
    client = _get_client()
    # Remove dependent rows first in case the schema has no ON DELETE CASCADE.
    # findings reference scan_snapshots, so they go before it.
    for table in ("findings", "scan_snapshots", "link_issues", "scans"):
        try:
            client.table(table).delete().eq("site_id", site_id).execute()
        except Exception as e:
            # A project that has not run migrations/001 has no findings table.
            print(f"[DB] delete from {table} skipped: {e}")
    resp = client.table("sites").delete().eq("id", site_id).execute()
    return resp.data


async def delete_site(site_id: str):
    import asyncio
    return await asyncio.to_thread(_delete_site_sync, site_id)