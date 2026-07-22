"""
Backfill the issues / issue_occurrences tables from historical scans.

Issues are DERIVED: this replays every site's scans in chronological order and
runs the same reconciliation the live path uses, so an issue's first_seen_at,
age, and fixed_at reflect real history — not the moment the backfill ran.

Idempotent: a site's issues are cleared and rebuilt from scratch each run, so it
is safe to re-run after a logic change. Non-destructive to everything else —
sites, scans, results and findings are only read.

Prerequisite: migration 025_issue_lifecycle.sql must be applied first.

Run from backend/:  python backfill_issues.py            (all sites)
                    python backfill_issues.py <site_id>   (one site)
"""
import sys

from database import _get_client, reconcile_and_persist_issues


def _scan_timestamp(scan: dict) -> str:
    # Scans carry scanned_at; fall back to created_at on older rows.
    return scan.get("scanned_at") or scan.get("created_at") or ""


def backfill_site(client, site) -> dict:
    site_id = site["id"]
    site_url = site.get("url") or ""

    # Idempotent: drop this site's derived issues; occurrences cascade.
    client.table("issues").delete().eq("site_id", site_id).execute()

    scans = (
        client.table("scans")
        .select("id, results_json, scanned_at, created_at")
        .eq("site_id", site_id)
        .order("scanned_at", desc=False)   # oldest first — history in order
        .execute()
    ).data or []

    replayed = 0
    for scan in scans:
        results = scan.get("results_json") or []
        if not results:
            continue
        now = _scan_timestamp(scan)
        reconcile_and_persist_issues(
            client, site_id, scan["id"], site_url, results, now=now or None
        )
        replayed += 1

    print(f"[backfill] {site_url or site_id}: replayed {replayed} scan(s)")
    return {"site_id": site_id, "scans": replayed}


def main(argv):
    client = _get_client()

    if len(argv) > 1:
        site = (
            client.table("sites").select("id, url").eq("id", argv[1]).execute()
        ).data
        sites = site or []
    else:
        sites = (client.table("sites").select("id, url").execute()).data or []

    if not sites:
        print("[backfill] no sites found")
        return

    total = 0
    for s in sites:
        try:
            total += backfill_site(client, s)["scans"]
        except Exception as e:
            print(f"[backfill] FAILED for {s.get('url') or s['id']}: {e}")

    print(f"[backfill] done — {len(sites)} site(s), {total} scan(s) replayed")


if __name__ == "__main__":
    main(sys.argv)
