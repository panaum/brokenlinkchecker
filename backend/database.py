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