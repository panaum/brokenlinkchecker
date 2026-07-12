"""Google Ads waste-guard: verify imported ad destinations and summarize.

Bucket discipline is inherited wholesale from the link checker — a 403 / bot-
block / timeout is **unverifiable**, never a breach. The one alarm we raise is
the provable one: a LIVE AD pointing at a provably DEAD page (a `broken`
bucket). Every hour that runs is spend burned, so it's the single finding class
that alerts immediately — after a flap-protected recheck.

Spend math is honest: only ever computed from imported cost, always labelled,
never invented.
"""
from datetime import datetime, timezone

import httpx

from checker import RawLink, check_single, bucket_for_label


def _dt(v):
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def verify_ad(url, client=None):
    """Return (status, response_ms, status_code) for one destination.
    status ∈ {ok, broken, unverifiable} — mapped through the checker's buckets."""
    link = RawLink(url=url, source_element="a", anchor_text="", category="Other",
                   is_external=True, zones=["Other"], link_kind="http")
    own = client is None
    if own:
        client = httpx.AsyncClient(follow_redirects=True, timeout=20)
    try:
        result = await check_single(client, link)
    finally:
        if own:
            await client.aclose()
    label = getattr(result, "label", None)
    bucket = bucket_for_label(label) if label else "unverifiable"
    status = "broken" if bucket == "broken" else ("ok" if bucket == "ok" else "unverifiable")
    return status, getattr(result, "response_ms", None), getattr(result, "status_code", None)


def summarize_guard(destinations, now=None):
    """Roll a site (or client) destination list into the guard dashboard payload.
    Pure — safe to unit-test."""
    now = now or datetime.now(timezone.utc)
    dests = destinations or []
    total = len(dests)
    ok = sum(1 for d in dests if d.get("status") == "ok")
    broken = sum(1 for d in dests if d.get("status") == "broken")
    unverifiable = sum(1 for d in dests if d.get("status") == "unverifiable")
    checked = sum(1 for d in dests if d.get("status") in ("ok", "broken", "unverifiable"))
    has_cost = any(d.get("cost_per_day") is not None for d in dests)

    last_checked = None
    for d in dests:
        c = _dt(d.get("last_checked_at"))
        if c and (last_checked is None or c > last_checked):
            last_checked = c

    breaches = []
    daily_at_risk = 0.0
    since_detected = 0.0
    for d in dests:
        if d.get("status") != "broken":
            continue
        cost = d.get("cost_per_day")
        b = {
            "id": d.get("id"), "campaign": d.get("campaign") or "Ungrouped",
            "ad_group": d.get("ad_group") or "", "final_url": d.get("final_url"),
            "cost_per_day": cost, "breach_since": d.get("breach_since"),
            "response_ms": d.get("response_ms"),
        }
        breaches.append(b)
        if has_cost and cost is not None:
            daily_at_risk += cost
            since = _dt(d.get("breach_since"))
            if since:
                days = max(0.0, (now - since).total_seconds() / 86400.0)
                since_detected += cost * days

    # Campaign grouping (healthy campaigns stay quiet; breached float up).
    by_campaign = {}
    for d in dests:
        by_campaign.setdefault(d.get("campaign") or "Ungrouped", []).append(d)
    campaigns = []
    for name, ds in by_campaign.items():
        campaigns.append({
            "name": name,
            "total": len(ds),
            "broken": sum(1 for x in ds if x.get("status") == "broken"),
            "unverifiable": sum(1 for x in ds if x.get("status") == "unverifiable"),
            "destinations": sorted(ds, key=lambda x: (x.get("status") != "broken", x.get("final_url") or "")),
        })
    campaigns.sort(key=lambda c: (c["broken"] == 0, c["name"]))  # breached campaigns first

    return {
        "total": total, "checked": checked, "ok": ok, "broken": broken, "unverifiable": unverifiable,
        "all_clear": total > 0 and broken == 0,
        "empty": total == 0,
        "last_checked": last_checked.isoformat() if last_checked else None,
        "has_cost": has_cost,
        "breaches": breaches,
        "spend": {
            "daily_at_risk": round(daily_at_risk, 2) if has_cost else None,
            "since_detected": round(since_detected, 2) if has_cost else None,
        },
        "campaigns": campaigns,
    }


async def run_ads_verification(notify=None):
    """Daily job: verify every imported destination for every site, update
    status, and fire ONE critical alert per NEW breach (flap-protected recheck
    before alerting). Returns a summary for logging.

    `notify(text)` is an async callable (Slack) — injected so this stays testable.
    """
    from database import sites_with_ads, list_ad_destinations, update_ad_status

    site_ids = await sites_with_ads()
    new_breaches = []
    checked = 0
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        for site_id in site_ids:
            dests = await list_ad_destinations(site_id)
            for d in dests:
                status, ms, _code = await verify_ad(d["final_url"], client=client)
                checked += 1
                was_broken = d.get("status") == "broken"
                if status == "broken" and not was_broken:
                    # Flap protection: confirm with one recheck before alerting.
                    status2, ms2, _ = await verify_ad(d["final_url"], client=client)
                    if status2 != "broken":
                        await update_ad_status(d["id"], status2, ms2, None)
                        continue
                    breach_since = datetime.now(timezone.utc).isoformat()
                    await update_ad_status(d["id"], "broken", ms2, breach_since)
                    new_breaches.append({**d, "breach_since": breach_since})
                elif status == "broken" and was_broken:
                    await update_ad_status(d["id"], "broken", ms, d.get("breach_since"))
                else:
                    await update_ad_status(d["id"], status, ms, None)

    if notify:
        for b in new_breaches:
            cost = b.get("cost_per_day")
            spend = f" · ≈ ${cost:g}/day of spend hitting a dead page" if cost is not None else ""
            text = (f":rotating_light: *LIVE AD → DEAD PAGE*  {b.get('campaign')}"
                    f"{' / ' + b['ad_group'] if b.get('ad_group') else ''}\n"
                    f"{b.get('final_url')}{spend}")
            try:
                await notify(text)
            except Exception:
                pass

    return {"sites": len(site_ids), "checked": checked, "new_breaches": len(new_breaches)}
