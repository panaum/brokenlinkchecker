import os
import threading
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


def _save_scan_sync(site_url, user_email, results, health_score):
    client = _get_client()
    
    total = len(results)
    broken = sum(1 for r in results if r.label == "broken")
    dead_cta = sum(1 for r in results if r.label == "dead_cta")
    redirect = sum(1 for r in results if r.label == "redirect")
    blocked = sum(1 for r in results if r.label == "blocked")

    # Insert site
    site_resp = client.table("sites").upsert({
        "url": site_url,
        "user_email": user_email,
        "last_scanned_at": "now()",
    }, on_conflict="url,user_email").execute()

    site_id = site_resp.data[0]["id"]

    # Save scan
    scan_resp = client.table("scans").insert({
        "site_id": site_id,
        "total_links": total,
        "broken_count": broken,
        "dead_cta_count": dead_cta,
        "redirect_count": redirect,
        "blocked_count": blocked,
        "health_score": health_score,
        "results_json": [r.dict() for r in results],
    }).execute()

    scan_id = scan_resp.data[0]["id"]

    # Save issues with uptime tracking
    for r in results:
        if r.label in ["broken", "dead_cta", "error"]:
            # Check if already exists
            existing = client.table("link_issues")\
                .select("id")\
                .eq("site_id", site_id)\
                .eq("url", r.url)\
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
                    "url": r.url,
                    "label": r.label,
                    "category": r.category,
                    "anchor_text": r.anchor_text,
                    "status_code": r.status_code,
                    "is_new": True,
                }).execute()

    # Mark resolved issues
    all_current_broken = {
        r.url for r in results
        if r.label in ["broken", "dead_cta", "error"]
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

    print(f"[DB] Saved scan for {site_url} — {total} links, score {health_score}")
    return {"site_id": site_id, "scan_id": scan_id}


def save_scan_threaded(site_url, user_email, results, health_score):
    """Run in a completely separate thread — no asyncio involvement."""
    result_container = {}
    error_container = {}

    def run():
        try:
            result_container["data"] = _save_scan_sync(
                site_url, user_email, results, health_score
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


async def save_scan(site_url, user_email, results, health_score):
    """Async wrapper that runs DB save in a real thread."""
    import asyncio
    return await asyncio.to_thread(
        save_scan_threaded, site_url, user_email, results, health_score
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