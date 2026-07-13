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


# The `findings` table's real columns. PostgREST rejects the ENTIRE batch if any
# row carries a key that is not a column, so the payload is whitelisted rather
# than trusted to match the model. snapshot_id/site_id are added at insert time.
FINDING_COLUMNS = frozenset({
    "fingerprint", "bucket", "confidence", "url", "anchor_text", "zone",
    "reason", "first_seen_at", "resolved_at", "status",
})

# The last snapshot-write failure, surfaced by /api/diagnostics/diffing so the
# real PostgREST error is one request away instead of buried in a server log.
_last_snapshot_error: Optional[dict] = None


def describe_exception(e: BaseException) -> dict:
    """Everything the exception knows.

    str(e) on a PostgREST APIError shows a short message and drops the code,
    details and hint — which is exactly where "row-level security policy" or
    "column ... does not exist" lives.
    """
    info = {
        "type": type(e).__name__,
        "str": str(e)[:600],
        "repr": repr(e)[:800],
        "args": [str(a)[:400] for a in getattr(e, "args", ())],
    }
    for attr in ("message", "code", "details", "hint"):
        value = getattr(e, attr, None)
        if value:
            info[attr] = str(value)[:400]
    return info


def last_snapshot_error() -> Optional[dict]:
    return _last_snapshot_error


def _record_snapshot_error(stage: str, e: BaseException, **extra) -> dict:
    global _last_snapshot_error
    _last_snapshot_error = {"stage": stage, **describe_exception(e), **extra}
    print(f"[Persist] {stage} FAILED: {_last_snapshot_error}")
    return _last_snapshot_error


def _finding_row(finding: dict, snapshot_id: str, site_id: str) -> dict:
    row = {k: v for k, v in finding.items() if k in FINDING_COLUMNS}
    row["snapshot_id"] = snapshot_id
    row["site_id"] = site_id
    return row


def _insert_findings(client, rows: list) -> int:
    """Batch insert; on failure retry one row at a time so the offending row is
    named instead of taking the whole scan's findings down with it."""
    if not rows:
        return 0
    try:
        client.table("findings").insert(rows).execute()
        return len(rows)
    except Exception as batch_error:
        _record_snapshot_error("findings.insert(batch)", batch_error,
                               row_count=len(rows), keys=sorted(rows[0]))
        print("[Persist] retrying findings one row at a time…")

    inserted = 0
    for i, row in enumerate(rows):
        try:
            client.table("findings").insert(row).execute()
            inserted += 1
        except Exception as row_error:
            _record_snapshot_error("findings.insert(row)", row_error,
                                   row_index=i, keys=sorted(row),
                                   fingerprint=row.get("fingerprint"))
    return inserted


def _save_snapshot_sync(site_id, scan_id, totals, findings, resolved) -> Optional[str]:
    global _last_snapshot_error
    client = _get_client()

    print(f"[Persist] snapshot attempt: site_id={site_id} scan_id={scan_id} "
          f"findings={len(findings or [])} fingerprints={len(totals.get('link_fingerprints') or [])}")

    # 1. The snapshot row. Without it there is nothing to attach findings to,
    #    so this is the only failure that is allowed to propagate.
    try:
        snap = client.table("scan_snapshots").insert({
            "site_id": site_id,
            "scan_id": scan_id,
            "totals_json": totals,
        }).execute()
        snapshot_id = snap.data[0]["id"]
    except Exception as e:
        _record_snapshot_error("scan_snapshots.insert", e,
                               site_id=site_id, scan_id=scan_id,
                               totals_keys=sorted(totals))
        raise

    # 2. Findings. A site with zero broken links legitimately has none, and a
    #    findings failure must not discard the snapshot we just wrote.
    rows = [_finding_row(f, snapshot_id, site_id) for f in (findings or [])]
    inserted = _insert_findings(client, rows)
    if rows and inserted < len(rows):
        print(f"[Persist] WARNING: only {inserted}/{len(rows)} findings inserted")

    # 3. Stamp findings that disappeared this scan. They live on their previous
    #    snapshot's rows, which is what the diff endpoint reads back.
    for fp, resolved_at in resolved or []:
        try:
            client.table("findings")\
                .update({"resolved_at": resolved_at, "status": "resolved"})\
                .eq("site_id", site_id)\
                .eq("fingerprint", fp)\
                .is_("resolved_at", "null")\
                .execute()
        except Exception as e:
            _record_snapshot_error("findings.update(resolved)", e, fingerprint=fp)

    if inserted == len(rows):
        _last_snapshot_error = None   # a clean write clears the last error

    print(f"[Persist] snapshot OK: id={snapshot_id} findings_inserted={inserted}")
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


# ─── Phase 6: fix verification ───────────────────────────────────────────────
_FINDING_COLUMNS_SELECT = (
    "id, site_id, snapshot_id, fingerprint, bucket, confidence, url, "
    "anchor_text, zone, reason, first_seen_at, resolved_at, status"
)


def _finding_lookup_sync(finding_id: str, site_id: str = "") -> Optional[dict]:
    """By database id, or — since the UI only ever holds a fingerprint — by
    (site_id, fingerprint). A fingerprint alone is not enough: it is scoped to a
    page, not to a site, so two sites could share one."""
    client = _get_client()

    try:
        resp = client.table("findings").select(_FINDING_COLUMNS_SELECT)\
            .eq("id", finding_id).limit(1).execute()
        if resp.data:
            return resp.data[0]
    except Exception:
        # Not a uuid: PostgREST rejects the cast. Fall through to fingerprint.
        pass

    if not site_id:
        return None

    resp = client.table("findings").select(_FINDING_COLUMNS_SELECT)\
        .eq("site_id", site_id).eq("fingerprint", finding_id)\
        .is_("resolved_at", "null").limit(1).execute()
    return resp.data[0] if resp.data else None


async def get_finding(finding_id: str, site_id: str = "") -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_finding_lookup_sync, finding_id, site_id)


def _mark_verified_sync(finding_id: str, resolved_at: str) -> dict:
    client = _get_client()
    resp = client.table("findings").update({
        "resolved_at": resolved_at,
        "status": "verified_fixed",
    }).eq("id", finding_id).execute()
    return (resp.data or [{}])[0]


async def mark_finding_verified(finding_id: str, resolved_at: str) -> dict:
    """Only ever called after a live re-check came back clean."""
    import asyncio
    return await asyncio.to_thread(_mark_verified_sync, finding_id, resolved_at)


def _site_url_sync(site_id: str) -> Optional[str]:
    client = _get_client()
    resp = client.table("sites").select("url").eq("id", site_id).limit(1).execute()
    return resp.data[0]["url"] if resp.data else None


async def get_site_url(site_id: str) -> Optional[str]:
    import asyncio
    return await asyncio.to_thread(_site_url_sync, site_id)


def _snapshot_write_probe_sync(site_url: str, user_email: str) -> dict:
    """Actually try to write a snapshot + finding, then delete them.

    A SELECT succeeding while an INSERT fails is the signature of row-level
    security with no policy, and reads alone cannot tell them apart. This does
    the write, reports the full PostgREST error, and cleans up after itself.
    """
    client = _get_client()

    site = client.table("sites").select("id")\
        .eq("url", site_url).eq("user_email", user_email).limit(1).execute()
    if not site.data:
        return {"ok": False, "stage": "sites.select",
                "error": {"str": "no sites row for this url + email"},
                "site_url": site_url, "user_email": user_email}
    site_id = site.data[0]["id"]

    snapshot_id = None
    try:
        snap = client.table("scan_snapshots").insert({
            "site_id": site_id,
            "scan_id": None,
            "totals_json": {"probe": True},
        }).execute()
        snapshot_id = snap.data[0]["id"]
    except Exception as e:
        return {"ok": False, "stage": "scan_snapshots.insert",
                "error": describe_exception(e), "site_id": site_id}

    try:
        client.table("findings").insert(_finding_row(
            {"fingerprint": "probe", "bucket": "broken", "url": "https://probe.invalid/",
             "status": "open"},
            snapshot_id, site_id,
        )).execute()
    except Exception as e:
        _cleanup_probe(client, snapshot_id)
        return {"ok": False, "stage": "findings.insert",
                "error": describe_exception(e), "site_id": site_id}

    cleanup = _cleanup_probe(client, snapshot_id)
    return {"ok": True, "site_id": site_id, "snapshot_id": snapshot_id,
            "cleaned_up": cleanup}


def _cleanup_probe(client, snapshot_id: str) -> object:
    """Remove the probe rows. findings cascade from scan_snapshots, but delete
    them explicitly in case the FK was created without ON DELETE CASCADE."""
    try:
        client.table("findings").delete().eq("snapshot_id", snapshot_id).execute()
        client.table("scan_snapshots").delete().eq("id", snapshot_id).execute()
        return True
    except Exception as e:
        return describe_exception(e)


async def snapshot_write_probe(site_url: str, user_email: str) -> dict:
    import asyncio
    return await asyncio.to_thread(_snapshot_write_probe_sync, site_url, user_email)


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


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9 — monitoring
#
# Additive only: one nullable column, sites.monitoring_enabled (migrations/002).
# The status/digest reads need no new storage — scan_snapshots.totals_json
# already carries health_score / new / fixed / findings with a created_at.
# ─────────────────────────────────────────────────────────────────────────────
def _monitored_sites_sync() -> list:
    client = _get_client()
    try:
        resp = client.table("sites")\
            .select("id, url, user_email, freq, monitoring_enabled")\
            .eq("monitoring_enabled", True)\
            .execute()
        return resp.data or []
    except Exception as e:
        # A project that has not run migrations/002 has no such column. Monitoring
        # is simply off until it does — never a crash on startup.
        print(f"[Monitor] could not load monitored sites: {e}")
        return []


async def get_monitored_sites() -> list:
    import asyncio
    return await asyncio.to_thread(_monitored_sites_sync)


class MonitoringColumnMissing(RuntimeError):
    """The sites.monitoring_enabled column does not exist — migrations/002 has
    not been applied. Raised with a message a user can act on, because the raw
    PostgREST error is the unhelpful string "Bad Request"."""


def _looks_like_missing_column(e: Exception) -> bool:
    detail = f"{describe_exception(e)}".lower()
    return "monitoring_enabled" in detail or ("column" in detail and "does not exist" in detail) \
        or "pgrst204" in detail or "42703" in detail


def _set_monitoring_sync(site_id: str, enabled: bool, freq: Optional[str]) -> dict:
    client = _get_client()
    patch = {"monitoring_enabled": enabled}
    if freq:
        patch["freq"] = freq
    try:
        resp = client.table("sites").update(patch).eq("id", site_id).execute()
    except Exception as e:
        if _looks_like_missing_column(e):
            raise MonitoringColumnMissing(
                "Monitoring is not set up in the database yet. Run migrations/002 "
                "in the Supabase SQL editor (adds the sites.monitoring_enabled "
                "column), then try again."
            ) from e
        raise
    return (resp.data or [{}])[0]


async def set_monitoring(site_id: str, enabled: bool, freq: Optional[str] = None) -> dict:
    import asyncio
    return await asyncio.to_thread(_set_monitoring_sync, site_id, enabled, freq)


def _site_by_id_sync(site_id: str) -> Optional[dict]:
    client = _get_client()
    try:
        resp = client.table("sites")\
            .select("id, url, user_email, freq, monitoring_enabled")\
            .eq("id", site_id).limit(1).execute()
    except Exception as e:
        # Before migrations/002 there is no monitoring_enabled column. Read what
        # exists so the status endpoint still works and can report "not set up".
        if not _looks_like_missing_column(e):
            raise
        resp = client.table("sites")\
            .select("id, url, user_email, freq")\
            .eq("id", site_id).limit(1).execute()
        if resp.data:
            resp.data[0]["monitoring_enabled"] = False
    return resp.data[0] if resp.data else None


async def get_site(site_id: str) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_site_by_id_sync, site_id)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — expected tracking ids (optional, per site)
#
# Additive: one nullable jsonb column, sites.expected_tracking (migrations/003).
# Holds {"ga4": "...", "meta_pixel": "...", "gtm": "..."}. When present, the
# tracking audit flags a page whose ids do not match. Every read is best-effort:
# before the migration there is no column, and that must never fail a scan.
# ─────────────────────────────────────────────────────────────────────────────
def _expected_tracking_sync(site_url: str, user_email: str) -> Optional[dict]:
    client = _get_client()
    try:
        resp = client.table("sites").select("expected_tracking")\
            .eq("url", site_url).eq("user_email", user_email).limit(1).execute()
    except Exception as e:
        if _looks_like_missing_column(e):
            return None
        raise
    if resp.data and resp.data[0].get("expected_tracking"):
        return resp.data[0]["expected_tracking"]
    return None


async def get_expected_tracking(site_url: str, user_email: str) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_expected_tracking_sync, site_url, user_email)


def _set_expected_tracking_sync(site_id: str, ids: dict) -> dict:
    client = _get_client()
    # Keep only the ids we audit; drop empties so "" never counts as configured.
    clean = {k: v for k, v in (ids or {}).items()
             if k in ("ga4", "meta_pixel", "gtm") and v}
    try:
        resp = client.table("sites").update({"expected_tracking": clean})\
            .eq("id", site_id).execute()
    except Exception as e:
        if _looks_like_missing_column(e):
            raise MonitoringColumnMissing(
                "Expected-tracking storage is not set up yet. Run migrations/003 "
                "in the Supabase SQL editor, then try again.")
        raise
    return (resp.data or [{}])[0]


async def set_expected_tracking(site_id: str, ids: dict) -> dict:
    import asyncio
    return await asyncio.to_thread(_set_expected_tracking_sync, site_id, ids)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7 — third-party watchdog (third_party_hosts + watchdog_alerts)
#
# All reads/writes are best-effort. Before migrations/004 the tables do not
# exist; a scan must never fail because the watchdog could not record a host.
# ─────────────────────────────────────────────────────────────────────────────
def _tables_missing(e: Exception) -> bool:
    detail = f"{describe_exception(e)}".lower()
    return ("third_party_hosts" in detail or "watchdog_alerts" in detail
            or "does not exist" in detail or "pgrst205" in detail
            or "42p01" in detail)


def _upsert_host_inventory_sync(site_id: str, records: list) -> int:
    if not site_id or not records:
        return 0
    client = _get_client()
    rows = [{
        "host": r["host"], "site_id": site_id,
        "resource_type": r.get("resource_type"),
        "last_status": "down" if r.get("down") else "up",
        "last_status_code": r.get("status"),
        "sample_url": r.get("sample_url"),
        "last_checked_at": "now()",
    } for r in records if r.get("host")]
    try:
        client.table("third_party_hosts").upsert(
            rows, on_conflict="host,site_id").execute()
        return len(rows)
    except Exception as e:
        if _tables_missing(e):
            print("[Watchdog] third_party_hosts missing — run migrations/004")
            return 0
        raise


async def upsert_host_inventory(site_id: str, records: list) -> int:
    import asyncio
    return await asyncio.to_thread(_upsert_host_inventory_sync, site_id, records)


def _watchdog_inventory_sync() -> list:
    """Every host row joined to its site, for aggregation and the endpoint."""
    client = _get_client()
    try:
        resp = client.table("third_party_hosts")\
            .select("host, resource_type, last_status, last_status_code, "
                    "sample_url, last_checked_at, sites(id, url, client)")\
            .execute()
    except Exception as e:
        if _tables_missing(e):
            return []
        raise
    out = []
    for row in resp.data or []:
        site = row.get("sites") or {}
        out.append({
            "host": row["host"],
            "resource_type": row.get("resource_type"),
            "status": row.get("last_status_code"),
            "down": row.get("last_status") == "down",
            "site_id": site.get("id"),
            "site_url": site.get("url"),
            "client": site.get("client"),
            "last_checked_at": row.get("last_checked_at"),
        })
    return out


async def get_watchdog_inventory() -> list:
    import asyncio
    return await asyncio.to_thread(_watchdog_inventory_sync)


def _recently_alerted_sync() -> dict:
    from datetime import datetime, timezone
    client = _get_client()
    try:
        resp = client.table("watchdog_alerts").select("host, last_alerted_at").execute()
    except Exception as e:
        if _tables_missing(e):
            return {}
        raise
    out = {}
    for row in resp.data or []:
        try:
            ts = datetime.fromisoformat(str(row["last_alerted_at"]).replace("Z", "+00:00"))
            out[row["host"]] = ts.timestamp()
        except Exception:
            continue
    return out


async def get_recently_alerted() -> dict:
    import asyncio
    return await asyncio.to_thread(_recently_alerted_sync)


def _record_host_alert_sync(host: str) -> None:
    client = _get_client()
    try:
        client.table("watchdog_alerts").upsert(
            {"host": host, "last_alerted_at": "now()"}, on_conflict="host").execute()
    except Exception as e:
        if not _tables_missing(e):
            raise


async def record_host_alert(host: str) -> None:
    import asyncio
    await asyncio.to_thread(_record_host_alert_sync, host)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — per-form active-testing opt-in (active_form_optin)
#
# A form is submittable by the active tester only if a row here says enabled.
# Best-effort reads: before migrations/005 the table does not exist, and that
# simply means no form is opted in — which is the safe default.
# ─────────────────────────────────────────────────────────────────────────────
def _form_optin_sync(site_id: str, form_key: str) -> Optional[dict]:
    client = _get_client()
    try:
        resp = client.table("active_form_optin")\
            .select("form_key, test_email, enabled")\
            .eq("site_id", site_id).eq("form_key", form_key).limit(1).execute()
    except Exception as e:
        if _tables_missing(e):
            return None
        raise
    return resp.data[0] if resp.data else None


async def get_form_optin(site_id: str, form_key: str) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_form_optin_sync, site_id, form_key)


def _set_form_optin_sync(site_id: str, form_key: str, enabled: bool,
                         test_email: Optional[str]) -> dict:
    client = _get_client()
    row = {"site_id": site_id, "form_key": form_key, "enabled": enabled,
           "updated_at": "now()"}
    if test_email is not None:
        row["test_email"] = test_email
    try:
        resp = client.table("active_form_optin").upsert(
            row, on_conflict="site_id,form_key").execute()
    except Exception as e:
        if _tables_missing(e):
            raise MonitoringColumnMissing(
                "Active-testing opt-in storage is not set up. Run migrations/005 "
                "in the Supabase SQL editor, then try again.")
        raise
    return (resp.data or [{}])[0]


async def set_form_optin(site_id: str, form_key: str, enabled: bool,
                         test_email: Optional[str] = None) -> dict:
    import asyncio
    return await asyncio.to_thread(_set_form_optin_sync, site_id, form_key,
                                   enabled, test_email)


def _list_form_optins_sync(site_id: str) -> list:
    client = _get_client()
    try:
        resp = client.table("active_form_optin")\
            .select("form_key, test_email, enabled, updated_at")\
            .eq("site_id", site_id).execute()
        return resp.data or []
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def list_form_optins(site_id: str) -> list:
    import asyncio
    return await asyncio.to_thread(_list_form_optins_sync, site_id)

# ─────────────────────────────────────────────────────────────────────────────
# Per-page third-party integrations (migrations/006_page_integrations.sql)
#
# Best-effort, like every other feature table: before the migration the table
# does not exist, and that must never fail a scan or an endpoint.
# ─────────────────────────────────────────────────────────────────────────────
def _save_integrations_sync(scan_id, page_url: str, records: list) -> int:
    if not records:
        return 0
    client = _get_client()
    rows = [{
        "scan_id": scan_id, "page_url": page_url,
        "host": r["host"], "resource_url": r["resource_url"],
        "category": r["category"], "type": r["type"],
        "detected_id": r.get("detected_id"),
        "health_status": r.get("health") or "checking",
        "last_checked_at": "now()" if r.get("health") not in (None, "checking") else None,
    } for r in records]
    try:
        client.table("page_integrations").upsert(
            rows, on_conflict="scan_id,page_url,host,resource_url,detected_id").execute()
        return len(rows)
    except Exception as e:
        if _tables_missing(e):
            print("[Integrations] page_integrations missing — run migrations/006")
            return 0
        raise


async def save_integrations(scan_id, page_url: str, records: list) -> int:
    import asyncio
    return await asyncio.to_thread(_save_integrations_sync, scan_id, page_url, records)


def _update_integration_health_sync(scan_id, resource_url: str, health: str) -> None:
    client = _get_client()
    try:
        client.table("page_integrations")\
            .update({"health_status": health, "last_checked_at": "now()"})\
            .eq("scan_id", scan_id).eq("resource_url", resource_url).execute()
    except Exception as e:
        if not _tables_missing(e):
            raise


async def update_integration_health(scan_id, resource_url: str, health: str) -> None:
    import asyncio
    await asyncio.to_thread(_update_integration_health_sync, scan_id, resource_url, health)


def _get_integrations_sync(scan_id, page_url: Optional[str]) -> list:
    client = _get_client()
    try:
        q = client.table("page_integrations")\
            .select("page_url, host, resource_url, category, type, detected_id, "
                    "health_status, last_checked_at")\
            .eq("scan_id", scan_id)
        if page_url:
            q = q.eq("page_url", page_url)
        return q.execute().data or []
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def get_integrations(scan_id, page_url: Optional[str] = None) -> list:
    import asyncio
    return await asyncio.to_thread(_get_integrations_sync, scan_id, page_url)


# ─────────────────────────────────────────────────────────────────────────────
# Wave 1: shareable client reports + status badge.
# All additive; every function tolerates the share_tokens table being absent
# (returns None / empty) so a deploy that hasn't run migration 002 still works.
# ─────────────────────────────────────────────────────────────────────────────

def _scan_row_sync(scan_id) -> Optional[dict]:
    """One scan's stored report + its site url. None if not found."""
    client = _get_client()
    try:
        resp = client.table("scans")\
            .select("id, site_id, total_links, broken_count, dead_cta_count, "
                    "redirect_count, health_score, results_json, scanned_at")\
            .eq("id", scan_id).limit(1).execute()
        rows = resp.data or []
        if not rows:
            return None
        scan = rows[0]
        url = ""
        try:
            site = client.table("sites").select("url")\
                .eq("id", scan["site_id"]).limit(1).execute()
            if site.data:
                url = site.data[0].get("url", "")
        except Exception:
            pass
        scan["url"] = url
        return scan
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def get_scan(scan_id) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_scan_row_sync, scan_id)


class ShareStorageMissing(Exception):
    """The share_tokens table doesn't exist — migration not applied."""


def _create_share_token_sync(scan_id, token: str) -> Optional[dict]:
    client = _get_client()
    scan = _scan_row_sync(scan_id)
    if not scan:
        return None  # genuinely no such scan (distinct from storage missing)
    try:
        client.table("share_tokens").insert({
            "token": token,
            "scan_id": scan_id,
            "site_id": scan.get("site_id"),
            "url": scan.get("url", ""),
        }).execute()
        return {"token": token, "url": scan.get("url", "")}
    except Exception as e:
        if _tables_missing(e):
            # The scan exists but the sharing table doesn't — actionable.
            raise ShareStorageMissing()
        raise


async def create_share_token(scan_id, token: str) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_create_share_token_sync, scan_id, token)


def _shared_report_sync(token: str) -> Optional[dict]:
    """The public report behind a share token, or None if missing/revoked."""
    client = _get_client()
    try:
        resp = client.table("share_tokens").select("scan_id, url, revoked")\
            .eq("token", token).limit(1).execute()
        rows = resp.data or []
        if not rows or rows[0].get("revoked"):
            return None
        scan = _scan_row_sync(rows[0]["scan_id"])
        if not scan:
            return None
        scan["url"] = scan.get("url") or rows[0].get("url", "")
        return scan
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def get_shared_report(token: str) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_shared_report_sync, token)


def _revoke_share_token_sync(token: str) -> bool:
    client = _get_client()
    try:
        client.table("share_tokens").update({"revoked": True})\
            .eq("token", token).execute()
        return True
    except Exception as e:
        if _tables_missing(e):
            return False
        raise


async def revoke_share_token(token: str) -> bool:
    import asyncio
    return await asyncio.to_thread(_revoke_share_token_sync, token)


def _latest_score_sync(site_id) -> Optional[dict]:
    """Latest scan's score + url for a site, for the status badge."""
    client = _get_client()
    try:
        resp = client.table("scans").select("health_score, scanned_at, site_id")\
            .eq("site_id", site_id).order("scanned_at", desc=True).limit(1).execute()
        rows = resp.data or []
        if not rows:
            return None
        out = {"health_score": rows[0].get("health_score")}
        try:
            site = client.table("sites").select("url").eq("id", site_id).limit(1).execute()
            out["url"] = site.data[0]["url"] if site.data else ""
        except Exception:
            out["url"] = ""
        return out
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def get_latest_score(site_id) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_latest_score_sync, site_id)


# ─────────────────────────────────────────────────────────────────────────────
# Client portal (P0): tenancy scope + membership resolution + backfill.
# All tolerant of migration 007 not being applied (return None / no-op), so the
# backend still imports and runs before the tables exist. Authorization is only
# enforced once routes are wrapped in a later step.
# ─────────────────────────────────────────────────────────────────────────────
STAFF_DOMAIN = "apexure.com"


def _site_scope_sync(site_id) -> Optional[dict]:
    client = _get_client()
    try:
        resp = client.table("sites").select("workspace_id, client_id")\
            .eq("id", site_id).limit(1).execute()
        rows = resp.data or []
        return rows[0] if rows else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def site_scope(site_id) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_site_scope_sync, site_id)


def _scan_scope_sync(scan_id) -> Optional[dict]:
    client = _get_client()
    try:
        resp = client.table("scans").select("site_id").eq("id", scan_id).limit(1).execute()
        rows = resp.data or []
        if not rows or not rows[0].get("site_id"):
            return None
        return _site_scope_sync(rows[0]["site_id"])
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def scan_scope(scan_id) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_scan_scope_sync, scan_id)


def _finding_scope_sync(finding_id) -> Optional[dict]:
    # Finding routes pass a fingerprint (not the row id) — match that first.
    client = _get_client()
    try:
        rows = client.table("findings").select("site_id")\
            .eq("fingerprint", finding_id).limit(1).execute().data or []
        if not rows:
            rows = client.table("findings").select("site_id")\
                .eq("id", finding_id).limit(1).execute().data or []
        if not rows or not rows[0].get("site_id"):
            return None
        return _site_scope_sync(rows[0]["site_id"])
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def finding_scope(finding_id) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_finding_scope_sync, finding_id)


def _resolve_membership_sync(email: str, workspace_id) -> Optional[dict]:
    """Membership of `email` in `workspace_id`. Auto-provisions @apexure.com
    staff as a `member` of an Apexure-owned workspace (preserves today's
    everyone-sees-everything behavior). Returns None for non-members."""
    client = _get_client()
    email = (email or "").strip().lower()
    if not email or not workspace_id:
        return None
    try:
        resp = client.table("memberships")\
            .select("user_email, workspace_id, role, client_id")\
            .eq("user_email", email).eq("workspace_id", workspace_id).limit(1).execute()
        rows = resp.data or []
        if rows:
            return rows[0]
        # Auto-join: staff email + staff-owned workspace -> create a member row.
        if email.endswith("@" + STAFF_DOMAIN):
            ws = client.table("workspaces").select("owner_email")\
                .eq("id", workspace_id).limit(1).execute().data or []
            owner = (ws[0].get("owner_email") if ws else "") or ""
            if owner.lower().endswith("@" + STAFF_DOMAIN):
                role = "owner" if owner.lower() == email else "member"
                client.table("memberships").insert({
                    "user_email": email, "workspace_id": workspace_id, "role": role,
                }).execute()
                return {"user_email": email, "workspace_id": workspace_id,
                        "role": role, "client_id": None}
        return None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def resolve_membership(email: str, workspace_id) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_resolve_membership_sync, email, workspace_id)


def _backfill_multitenancy_sync(owner_email: str) -> dict:
    """Create the single Apexure workspace (if absent), attach every workspace-less
    site to it, and seed the owner membership. Idempotent."""
    client = _get_client()
    owner_email = (owner_email or "").strip().lower()
    # 1. Find or create the Apexure workspace.
    existing = client.table("workspaces").select("id, owner_email")\
        .eq("name", "Apexure").limit(1).execute().data or []
    if existing:
        ws_id = existing[0]["id"]
    else:
        created = client.table("workspaces").insert({
            "name": "Apexure", "owner_email": owner_email,
        }).execute()
        ws_id = created.data[0]["id"]
    # 2. Attach every site that has no workspace yet.
    client.table("sites").update({"workspace_id": ws_id})\
        .is_("workspace_id", "null").execute()
    # 3. Seed owner membership.
    have = client.table("memberships").select("id")\
        .eq("user_email", owner_email).eq("workspace_id", ws_id).limit(1).execute().data or []
    if not have:
        client.table("memberships").insert({
            "user_email": owner_email, "workspace_id": ws_id, "role": "owner",
        }).execute()
    attached = client.table("sites").select("id", count="exact")\
        .eq("workspace_id", ws_id).execute()
    return {"workspace_id": ws_id, "sites_attached": attached.count}


async def backfill_multitenancy(owner_email: str) -> dict:
    import asyncio
    return await asyncio.to_thread(_backfill_multitenancy_sync, owner_email)


def _any_membership_sync(email: str) -> Optional[dict]:
    """The caller's membership for a non-site-scoped agency route. Highest role
    first; auto-provisions @apexure.com staff into the Apexure workspace."""
    client = _get_client()
    email = (email or "").strip().lower()
    if not email:
        return None
    try:
        rows = client.table("memberships")\
            .select("user_email, workspace_id, role, client_id")\
            .eq("user_email", email).execute().data or []
        if rows:
            rank = {"owner": 3, "member": 2, "client_viewer": 1}
            return sorted(rows, key=lambda r: rank.get(r.get("role"), 0), reverse=True)[0]
        if email.endswith("@" + STAFF_DOMAIN):
            ws = client.table("workspaces").select("id, owner_email")\
                .eq("name", "Apexure").limit(1).execute().data or []
            if ws and (ws[0].get("owner_email") or "").lower().endswith("@" + STAFF_DOMAIN):
                return _resolve_membership_sync(email, ws[0]["id"])
        return None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def any_membership(email: str) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_any_membership_sync, email)


# ─────────────────────────────────────────────────────────────────────────────
# Client portal: clients, invites, audit. All tolerant of migration 007 absent.
# ─────────────────────────────────────────────────────────────────────────────
def _staff_workspace_id_sync() -> Optional[str]:
    """The Apexure workspace id — the acting workspace when enforcement is off."""
    client = _get_client()
    try:
        rows = client.table("workspaces").select("id").eq("name", "Apexure")\
            .limit(1).execute().data or []
        return rows[0]["id"] if rows else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def staff_workspace_id() -> Optional[str]:
    import asyncio
    return await asyncio.to_thread(_staff_workspace_id_sync)


def _create_client_sync(workspace_id: str, name: str) -> Optional[dict]:
    client = _get_client()
    try:
        r = client.table("clients").insert({"workspace_id": workspace_id, "name": name}).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def create_client(workspace_id: str, name: str) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_create_client_sync, workspace_id, name)


def _list_clients_sync(workspace_id: str) -> list:
    client = _get_client()
    try:
        return client.table("clients").select("id, name, created_at")\
            .eq("workspace_id", workspace_id).order("name").execute().data or []
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def list_clients(workspace_id: str) -> list:
    import asyncio
    return await asyncio.to_thread(_list_clients_sync, workspace_id)


def _assign_site_client_sync(site_id: str, client_id) -> bool:
    client = _get_client()
    try:
        client.table("sites").update({"client_id": client_id}).eq("id", site_id).execute()
        return True
    except Exception as e:
        if _tables_missing(e):
            return False
        raise


async def assign_site_client(site_id: str, client_id) -> bool:
    import asyncio
    return await asyncio.to_thread(_assign_site_client_sync, site_id, client_id)


def _create_invite_sync(workspace_id, client_id, email, role, token, expires_at) -> Optional[dict]:
    client = _get_client()
    try:
        client.table("invites").insert({
            "token": token, "workspace_id": workspace_id, "client_id": client_id,
            "email": (email or "").strip().lower(), "role": role, "expires_at": expires_at,
        }).execute()
        return {"token": token, "email": email, "client_id": client_id, "expires_at": expires_at}
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def create_invite(workspace_id, client_id, email, role, token, expires_at) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_create_invite_sync, workspace_id, client_id, email, role, token, expires_at)


def _accept_invite_sync(token: str, now_iso: str) -> Optional[dict]:
    """Validate + consume an invite, create the client_viewer membership. Returns
    {email, workspace_id, client_id, role, reason?} — reason set on rejection."""
    client = _get_client()
    try:
        rows = client.table("invites")\
            .select("workspace_id, client_id, email, role, expires_at, accepted_at, revoked")\
            .eq("token", token).limit(1).execute().data or []
        if not rows:
            return {"reason": "not_found"}
        inv = rows[0]
        if inv.get("revoked"):
            return {"reason": "revoked"}
        if inv.get("accepted_at"):
            return {"reason": "used"}
        if inv.get("expires_at") and str(inv["expires_at"]) < now_iso:
            return {"reason": "expired"}
        email = (inv.get("email") or "").strip().lower()
        # Upsert the membership (client_viewer, scoped to the invite's client).
        existing = client.table("memberships").select("id")\
            .eq("user_email", email).eq("workspace_id", inv["workspace_id"]).limit(1).execute().data or []
        payload = {"user_email": email, "workspace_id": inv["workspace_id"],
                   "role": inv.get("role") or "client_viewer", "client_id": inv.get("client_id")}
        if existing:
            client.table("memberships").update(payload).eq("id", existing[0]["id"]).execute()
        else:
            client.table("memberships").insert(payload).execute()
        client.table("invites").update({"accepted_at": now_iso}).eq("token", token).execute()
        return {"email": email, "workspace_id": inv["workspace_id"],
                "client_id": inv.get("client_id"), "role": payload["role"]}
    except Exception as e:
        if _tables_missing(e):
            return {"reason": "storage_unavailable"}
        raise


async def accept_invite(token: str, now_iso: str) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_accept_invite_sync, token, now_iso)


def _revoke_invite_sync(token: str) -> bool:
    client = _get_client()
    try:
        client.table("invites").update({"revoked": True}).eq("token", token).execute()
        return True
    except Exception as e:
        if _tables_missing(e):
            return False
        raise


async def revoke_invite(token: str) -> bool:
    import asyncio
    return await asyncio.to_thread(_revoke_invite_sync, token)


def _list_invites_sync(workspace_id: str) -> list:
    client = _get_client()
    try:
        return client.table("invites")\
            .select("token, email, client_id, role, created_at, expires_at, accepted_at, revoked")\
            .eq("workspace_id", workspace_id).order("created_at", desc=True).execute().data or []
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def list_invites(workspace_id: str) -> list:
    import asyncio
    return await asyncio.to_thread(_list_invites_sync, workspace_id)


def _write_audit_sync(workspace_id, user_email, action, site_id=None) -> None:
    client = _get_client()
    try:
        client.table("audit_log").insert({
            "workspace_id": workspace_id, "user_email": (user_email or "").lower(),
            "action": action, "site_id": site_id,
        }).execute()
    except Exception as e:
        if not _tables_missing(e):
            raise  # audit is best-effort; a missing table must never break a request


async def write_audit(workspace_id, user_email, action, site_id=None) -> None:
    import asyncio
    await asyncio.to_thread(_write_audit_sync, workspace_id, user_email, action, site_id)


def _list_audit_sync(workspace_id: str, limit: int = 100) -> list:
    client = _get_client()
    try:
        return client.table("audit_log").select("user_email, action, site_id, at")\
            .eq("workspace_id", workspace_id).order("at", desc=True).limit(limit).execute().data or []
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def list_audit(workspace_id: str, limit: int = 100) -> list:
    import asyncio
    return await asyncio.to_thread(_list_audit_sync, workspace_id, limit)


# ─── Client portal: per-client Resources (labeled links) ─────────────────────
def _create_resource_sync(client_id, workspace_id, title, url, visible) -> Optional[dict]:
    client = _get_client()
    try:
        r = client.table("client_resources").insert({
            "client_id": client_id, "workspace_id": workspace_id,
            "title": title, "url": url, "visible": bool(visible),
        }).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def create_resource(client_id, workspace_id, title, url, visible=True) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_create_resource_sync, client_id, workspace_id, title, url, visible)


def _list_resources_sync(client_id, visible_only: bool) -> list:
    client = _get_client()
    try:
        q = client.table("client_resources")\
            .select("id, title, url, visible, created_at").eq("client_id", client_id)
        if visible_only:
            q = q.eq("visible", True)
        return q.order("created_at").execute().data or []
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def list_resources(client_id, visible_only: bool = False) -> list:
    import asyncio
    return await asyncio.to_thread(_list_resources_sync, client_id, visible_only)


def _update_resource_sync(resource_id, patch: dict) -> bool:
    client = _get_client()
    try:
        client.table("client_resources").update(patch).eq("id", resource_id).execute()
        return True
    except Exception as e:
        if _tables_missing(e):
            return False
        raise


async def set_resource_visible(resource_id, visible: bool) -> bool:
    import asyncio
    return await asyncio.to_thread(_update_resource_sync, resource_id, {"visible": bool(visible)})


async def delete_resource(resource_id) -> bool:
    import asyncio
    def _del():
        client = _get_client()
        try:
            client.table("client_resources").delete().eq("id", resource_id).execute()
            return True
        except Exception as e:
            if _tables_missing(e):
                return False
            raise
    return await asyncio.to_thread(_del)


# ─── Wave 1: vigilance reports (data source + persistence) ───────────────────
def _report_source_sync(site_id) -> dict:
    """Scans + findings + form/integration counts for a site's report."""
    client = _get_client()
    scans = client.table("scans")\
        .select("id, scanned_at, health_score, total_links, broken_count, dead_cta_count")\
        .eq("site_id", site_id).order("scanned_at", desc=True).limit(180).execute().data or []
    findings = client.table("findings")\
        .select("fingerprint, bucket, url, anchor_text, zone, reason, first_seen_at, resolved_at, status")\
        .eq("site_id", site_id).limit(500).execute().data or []
    forms = 0
    integrations = 0
    if scans:
        latest_id = scans[0]["id"]
        try:
            rj = client.table("scans").select("results_json").eq("id", latest_id).limit(1).execute().data
            results = (rj[0].get("results_json") if rj else None) or []
            forms = sum(1 for r in results if isinstance(r, dict) and r.get("resource_type") == "form_action")
        except Exception:
            forms = 0
        try:
            pi = client.table("page_integrations").select("id", count="exact").eq("scan_id", latest_id).execute()
            integrations = pi.count or 0
        except Exception:
            integrations = 0
    return {"scans": scans, "findings": findings, "forms_audited": forms, "integrations_watched": integrations}


async def report_source(site_id) -> dict:
    import asyncio
    return await asyncio.to_thread(_report_source_sync, site_id)


def _save_report_sync(site_id, period_start, period_end, label, data) -> Optional[dict]:
    client = _get_client()
    try:
        row = {"site_id": site_id, "period_start": period_start, "period_end": period_end,
               "period_label": label, "data_json": data}
        # Upsert on (site_id, period_label) so a re-generate replaces, not duplicates.
        r = client.table("vigilance_reports").upsert(row, on_conflict="site_id,period_label").execute()
        return r.data[0] if r.data else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def save_report(site_id, period_start, period_end, label, data) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_save_report_sync, site_id, period_start, period_end, label, data)


def _list_reports_sync(site_id) -> list:
    client = _get_client()
    try:
        return client.table("vigilance_reports")\
            .select("id, period_label, period_start, created_at, data_json")\
            .eq("site_id", site_id).order("period_start", desc=True).execute().data or []
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def list_reports(site_id) -> list:
    import asyncio
    return await asyncio.to_thread(_list_reports_sync, site_id)


def _get_report_sync(report_id) -> Optional[dict]:
    client = _get_client()
    try:
        rows = client.table("vigilance_reports")\
            .select("id, site_id, period_label, period_start, period_end, data_json, created_at")\
            .eq("id", report_id).limit(1).execute().data or []
        return rows[0] if rows else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def get_report(report_id) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_get_report_sync, report_id)


def _reports_for_client_sync(client_id) -> list:
    """Reports across all sites of a client (portal archive)."""
    client = _get_client()
    try:
        sites = client.table("sites").select("id, url, name").eq("client_id", client_id).execute().data or []
        ids = [s["id"] for s in sites]
        if not ids:
            return []
        rows = client.table("vigilance_reports")\
            .select("id, site_id, period_label, period_start, created_at, data_json")\
            .in_("site_id", ids).order("period_start", desc=True).execute().data or []
        by_site = {s["id"]: (s.get("name") or s.get("url")) for s in sites}
        for r in rows:
            r["site_name"] = by_site.get(r["site_id"], "")
        return rows
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def reports_for_client(client_id) -> list:
    import asyncio
    return await asyncio.to_thread(_reports_for_client_sync, client_id)


# ─── Wave 2: Google Ads waste-guard (imported destinations) ──────────────────
import hashlib as _hashlib


def _ad_fingerprint(campaign, ad_group, final_url) -> str:
    raw = f"{campaign}|{ad_group}|{final_url}".encode("utf-8", "ignore")
    return _hashlib.sha1(raw).hexdigest()


def _replace_ad_destinations_sync(site_id, destinations) -> dict:
    """A fresh import replaces the current picture (delete + insert)."""
    client = _get_client()
    try:
        client.table("ad_destinations").delete().eq("site_id", site_id).execute()
        rows = []
        for d in destinations:
            fp = _ad_fingerprint(d["campaign"], d.get("ad_group", ""), d["final_url"])
            rows.append({
                "site_id": site_id, "campaign": d["campaign"], "ad_group": d.get("ad_group", ""),
                "final_url": d["final_url"], "cost_per_day": d.get("cost_per_day"),
                "status": "unchecked", "fingerprint": fp,
            })
        if rows:
            client.table("ad_destinations").insert(rows).execute()
        return {"imported": len(rows)}
    except Exception as e:
        if _tables_missing(e):
            return {"imported": 0, "setup_required": True}
        raise


async def replace_ad_destinations(site_id, destinations) -> dict:
    import asyncio
    return await asyncio.to_thread(_replace_ad_destinations_sync, site_id, destinations)


def _list_ad_destinations_sync(site_id) -> list:
    client = _get_client()
    try:
        return client.table("ad_destinations").select(
            "id, campaign, ad_group, final_url, cost_per_day, status, response_ms, "
            "last_checked_at, breach_since, imported_at"
        ).eq("site_id", site_id).order("campaign").execute().data or []
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def list_ad_destinations(site_id) -> list:
    import asyncio
    return await asyncio.to_thread(_list_ad_destinations_sync, site_id)


def _update_ad_status_sync(dest_id, status, response_ms, breach_since) -> None:
    from datetime import datetime, timezone
    client = _get_client()
    patch = {"status": status, "response_ms": response_ms,
             "last_checked_at": datetime.now(timezone.utc).isoformat(), "breach_since": breach_since}
    client.table("ad_destinations").update(patch).eq("id", dest_id).execute()


async def update_ad_status(dest_id, status, response_ms, breach_since) -> None:
    import asyncio
    await asyncio.to_thread(_update_ad_status_sync, dest_id, status, response_ms, breach_since)


def _sites_with_ads_sync() -> list:
    client = _get_client()
    try:
        rows = client.table("ad_destinations").select("site_id").execute().data or []
        return sorted({r["site_id"] for r in rows})
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def sites_with_ads() -> list:
    import asyncio
    return await asyncio.to_thread(_sites_with_ads_sync)


def _ad_destinations_for_client_sync(client_id) -> list:
    client = _get_client()
    try:
        sites = client.table("sites").select("id, url, name").eq("client_id", client_id).execute().data or []
        ids = [s["id"] for s in sites]
        if not ids:
            return []
        rows = client.table("ad_destinations").select(
            "id, site_id, campaign, ad_group, final_url, cost_per_day, status, response_ms, "
            "last_checked_at, breach_since, imported_at"
        ).in_("site_id", ids).order("campaign").execute().data or []
        return rows
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def ad_destinations_for_client(client_id) -> list:
    import asyncio
    return await asyncio.to_thread(_ad_destinations_for_client_sync, client_id)


# ─── Wave 3: Disaster Sentinel ───────────────────────────────────────────────
def _sentinel_status_sync(site_id) -> Optional[dict]:
    client = _get_client()
    try:
        rows = client.table("sentinel_status").select("*").eq("site_id", site_id).limit(1).execute().data or []
        return rows[0] if rows else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def get_sentinel_status(site_id) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_sentinel_status_sync, site_id)


def _upsert_sentinel_status_sync(site_id, patch) -> Optional[dict]:
    client = _get_client()
    try:
        row = {"site_id": site_id, **patch}
        r = client.table("sentinel_status").upsert(row, on_conflict="site_id").execute()
        return r.data[0] if r.data else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def upsert_sentinel_status(site_id, patch) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_upsert_sentinel_status_sync, site_id, patch)


def _add_uptime_ping_sync(site_id, up) -> None:
    client = _get_client()
    try:
        client.table("uptime_pings").insert({"site_id": site_id, "up": bool(up)}).execute()
    except Exception as e:
        if not _tables_missing(e):
            raise


async def add_uptime_ping(site_id, up) -> None:
    import asyncio
    await asyncio.to_thread(_add_uptime_ping_sync, site_id, up)


def _recent_pings_sync(site_id, limit=8640) -> list:
    client = _get_client()
    try:
        rows = client.table("uptime_pings").select("up, at").eq("site_id", site_id)\
            .order("at", desc=True).limit(limit).execute().data or []
        return [bool(r["up"]) for r in rows]
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def recent_pings(site_id, limit=8640) -> list:
    import asyncio
    return await asyncio.to_thread(_recent_pings_sync, site_id, limit)


def _open_incident_sync(site_id) -> None:
    from datetime import datetime, timezone
    client = _get_client()
    try:
        # don't stack: only open if there's no currently-open incident
        openrows = client.table("sentinel_incidents").select("id").eq("site_id", site_id)\
            .is_("restored_at", "null").limit(1).execute().data or []
        if not openrows:
            client.table("sentinel_incidents").insert(
                {"site_id": site_id, "down_at": datetime.now(timezone.utc).isoformat()}).execute()
    except Exception as e:
        if not _tables_missing(e):
            raise


async def open_incident(site_id) -> None:
    import asyncio
    await asyncio.to_thread(_open_incident_sync, site_id)


def _close_incident_sync(site_id) -> bool:
    from datetime import datetime, timezone
    client = _get_client()
    try:
        openrows = client.table("sentinel_incidents").select("id").eq("site_id", site_id)\
            .is_("restored_at", "null").order("down_at", desc=True).limit(1).execute().data or []
        if openrows:
            client.table("sentinel_incidents").update(
                {"restored_at": datetime.now(timezone.utc).isoformat()}).eq("id", openrows[0]["id"]).execute()
            return True
        return False
    except Exception as e:
        if _tables_missing(e):
            return False
        raise


async def close_incident(site_id) -> bool:
    import asyncio
    return await asyncio.to_thread(_close_incident_sync, site_id)


def _list_incidents_sync(site_id, limit=50) -> list:
    client = _get_client()
    try:
        return client.table("sentinel_incidents").select("id, down_at, restored_at")\
            .eq("site_id", site_id).order("down_at", desc=True).limit(limit).execute().data or []
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def list_incidents(site_id, limit=50) -> list:
    import asyncio
    return await asyncio.to_thread(_list_incidents_sync, site_id, limit)


def _all_sites_min_sync() -> list:
    client = _get_client()
    try:
        return client.table("sites").select("id, url").execute().data or []
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def all_sites_min() -> list:
    import asyncio
    return await asyncio.to_thread(_all_sites_min_sync)


def _site_url_sync(site_id) -> str:
    client = _get_client()
    try:
        rows = client.table("sites").select("url").eq("id", site_id).limit(1).execute().data or []
        return rows[0].get("url", "") if rows else ""
    except Exception:
        return ""


async def get_site_url(site_id) -> str:
    import asyncio
    return await asyncio.to_thread(_site_url_sync, site_id)


# ─── Verified Lead Delivery, Wave 1: form contracts + run ledger ─────────────
def _next_contract_version_sync(client, contract_key) -> int:
    rows = client.table("form_contracts").select("version").eq("contract_key", contract_key)\
        .order("version", desc=True).limit(1).execute().data or []
    return (rows[0]["version"] + 1) if rows else 1


def _save_contract_version_sync(site_id, contract_key, status, draft, confirmed_by=None) -> Optional[dict]:
    """Append a new immutable version row (draft/confirmed/archived)."""
    from datetime import datetime, timezone
    client = _get_client()
    try:
        v = _next_contract_version_sync(client, contract_key)
        row = {
            "site_id": site_id, "contract_key": contract_key, "version": v, "status": status,
            "form_ref": draft.get("form_ref", {}), "fields": draft.get("fields", []),
            "destination": draft.get("destination", {}), "events": draft.get("events", []),
        }
        if status == "confirmed":
            row["confirmed_by"] = confirmed_by
            row["confirmed_at"] = datetime.now(timezone.utc).isoformat()
        r = client.table("form_contracts").insert(row).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def save_contract_version(site_id, contract_key, status, draft, confirmed_by=None) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_save_contract_version_sync, site_id, contract_key, status, draft, confirmed_by)


def _list_contracts_sync(site_id) -> list:
    """Latest version per contract_key for a site (the live contracts)."""
    client = _get_client()
    try:
        rows = client.table("form_contracts").select("*").eq("site_id", site_id)\
            .order("version", desc=True).execute().data or []
        latest = {}
        for r in rows:
            k = r["contract_key"]
            if k not in latest:      # rows are version-desc, first seen = newest
                latest[k] = r
        return list(latest.values())
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def list_contracts(site_id) -> list:
    import asyncio
    return await asyncio.to_thread(_list_contracts_sync, site_id)


def _get_contract_sync(contract_id) -> Optional[dict]:
    client = _get_client()
    try:
        rows = client.table("form_contracts").select("*").eq("id", contract_id).limit(1).execute().data or []
        return rows[0] if rows else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def get_contract(contract_id) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_get_contract_sync, contract_id)


def _confirmed_contracts_sync(site_id) -> list:
    """Latest CONFIRMED version per key — the contracts drift is checked against."""
    return [c for c in _list_contracts_sync(site_id) if c.get("status") == "confirmed"]


async def confirmed_contracts(site_id) -> list:
    import asyncio
    return await asyncio.to_thread(_confirmed_contracts_sync, site_id)


def _insert_tracer_run_sync(run: dict) -> Optional[dict]:
    """Append one immutable ledger row (written by Wave 2)."""
    client = _get_client()
    try:
        r = client.table("tracer_runs").insert(run).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def insert_tracer_run(run: dict) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_insert_tracer_run_sync, run)


# ─── Verified Lead Delivery, Wave 2: CRM connections + enrollments + runs ────
def _save_crm_connection_sync(site_id, crm_type, credentials_enc, test_ok, test_detail) -> Optional[dict]:
    from datetime import datetime, timezone
    client = _get_client()
    try:
        row = {"site_id": site_id, "crm_type": crm_type, "credentials_enc": credentials_enc,
               "test_ok": test_ok, "test_detail": test_detail,
               "last_tested_at": datetime.now(timezone.utc).isoformat()}
        r = client.table("crm_connections").upsert(row, on_conflict="site_id,crm_type").execute()
        return r.data[0] if r.data else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def save_crm_connection(site_id, crm_type, credentials_enc, test_ok, test_detail) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_save_crm_connection_sync, site_id, crm_type, credentials_enc, test_ok, test_detail)


def _get_crm_connection_sync(site_id) -> Optional[dict]:
    client = _get_client()
    try:
        rows = client.table("crm_connections").select("*").eq("site_id", site_id).limit(1).execute().data or []
        return rows[0] if rows else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def get_crm_connection(site_id) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_get_crm_connection_sync, site_id)


def _save_enrollment_sync(site_id, contract_key, patch) -> Optional[dict]:
    client = _get_client()
    try:
        row = {"site_id": site_id, "contract_key": contract_key, **patch}
        r = client.table("tracer_enrollments").upsert(row, on_conflict="site_id,contract_key").execute()
        return r.data[0] if r.data else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def save_enrollment(site_id, contract_key, patch) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_save_enrollment_sync, site_id, contract_key, patch)


def _get_enrollment_sync(site_id, contract_key) -> Optional[dict]:
    client = _get_client()
    try:
        rows = client.table("tracer_enrollments").select("*").eq("site_id", site_id)\
            .eq("contract_key", contract_key).limit(1).execute().data or []
        return rows[0] if rows else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def get_enrollment(site_id, contract_key) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_get_enrollment_sync, site_id, contract_key)


def _list_enrollments_sync(site_id) -> list:
    client = _get_client()
    try:
        return client.table("tracer_enrollments").select("*").eq("site_id", site_id).execute().data or []
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def list_enrollments(site_id) -> list:
    import asyncio
    return await asyncio.to_thread(_list_enrollments_sync, site_id)


def _active_enrollments_sync() -> list:
    client = _get_client()
    try:
        return client.table("tracer_enrollments").select("*")\
            .eq("enabled", True).eq("schedule_active", True).execute().data or []
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def active_enrollments() -> list:
    import asyncio
    return await asyncio.to_thread(_active_enrollments_sync)


def _runs_for_site_sync(site_id, limit=200) -> list:
    client = _get_client()
    try:
        return client.table("tracer_runs").select(
            "id, contract_id, contract_version, started_at, mode, outcome, arrival, cleanup, duration_ms, evidence"
        ).eq("site_id", site_id).order("started_at", desc=True).limit(limit).execute().data or []
    except Exception as e:
        if _tables_missing(e):
            return []
        raise


async def runs_for_site(site_id, limit=200) -> list:
    import asyncio
    return await asyncio.to_thread(_runs_for_site_sync, site_id, limit)


def _mark_cleanup_sync(run_id, status) -> None:
    """The ONLY permitted mutation of a ledger row (enforced by DB trigger)."""
    client = _get_client()
    try:
        client.table("tracer_runs").update({"cleanup": status}).eq("id", run_id).execute()
    except Exception as e:
        if not _tables_missing(e):
            raise


async def mark_cleanup(run_id, status) -> None:
    import asyncio
    await asyncio.to_thread(_mark_cleanup_sync, run_id, status)


# ─── Insight Layer, PR1: latest scan for the intent map ──────────────────────
def _latest_scan_for_site_sync(site_id) -> Optional[dict]:
    client = _get_client()
    try:
        rows = client.table("scans").select("id, results_json, scanned_at")\
            .eq("site_id", site_id).order("scanned_at", desc=True).limit(1).execute().data or []
        return rows[0] if rows else None
    except Exception as e:
        if _tables_missing(e):
            return None
        raise


async def latest_scan_for_site(site_id) -> Optional[dict]:
    import asyncio
    return await asyncio.to_thread(_latest_scan_for_site_sync, site_id)
