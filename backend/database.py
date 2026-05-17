import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


async def save_scan(
    site_url: str,
    user_email: str,
    results: list,
    health_score: int,
) -> dict:
    total = len(results)
    broken = sum(1 for r in results if r.label == "broken")
    dead_cta = sum(1 for r in results if r.label == "dead_cta")
    redirect = sum(1 for r in results if r.label == "redirect")
    blocked = sum(1 for r in results if r.label == "blocked")

    # Upsert site
    site_resp = supabase.table("sites").upsert({
        "url": site_url,
        "user_email": user_email,
        "last_scanned_at": "now()",
    }, on_conflict="url,user_email").execute()

    site_id = site_resp.data[0]["id"]

    # Save scan
    scan_resp = supabase.table("scans").insert({
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

    # Save individual issues
    issues = []
    for r in results:
        if r.label in ["broken", "dead_cta", "error"]:
            issues.append({
                "site_id": site_id,
                "scan_id": scan_id,
                "url": r.url,
                "label": r.label,
                "category": r.category,
                "anchor_text": r.anchor_text,
                "status_code": r.status_code,
            })

    if issues:
        supabase.table("link_issues").insert(issues).execute()

    return {"site_id": site_id, "scan_id": scan_id}


async def get_previous_scan(site_id: str) -> dict | None:
    resp = supabase.table("scans")\
        .select("*")\
        .eq("site_id", site_id)\
        .order("scanned_at", desc=True)\
        .limit(2)\
        .execute()

    if len(resp.data) < 2:
        return None

    return resp.data[1]  # second most recent = previous


async def get_site_history(site_url: str, user_email: str) -> list:
    resp = supabase.table("scans")\
        .select("*, sites!inner(url, user_email)")\
        .eq("sites.url", site_url)\
        .eq("sites.user_email", user_email)\
        .order("scanned_at", desc=True)\
        .limit(30)\
        .execute()

    return resp.data
