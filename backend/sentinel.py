"""Disaster Sentinel: SSL / domain expiry, indexability, uptime.

The "nothing catastrophic without warning" tier. Two halves:
  • Pure logic (expiry-day math, escalation tiers, alert-ladder crossings,
    indexability verdict, downtime from pings, uptime %) — trivially testable.
  • Network probes (TLS handshake, RDAP, robots/noindex/sitemap, HEAD ping).

Honesty rules, hard: never fabricate an expiry date. Some TLDs hide domain
expiry over RDAP/WHOIS — that surfaces as "unavailable", not a guessed date.
An expiry we cannot read is `None`, and the UI says so.
"""
from datetime import datetime, timezone

# Alert ladder thresholds (days). Escalating copy at each; change-only.
LADDER = (30, 14, 3)


def _now(now=None):
    return now or datetime.now(timezone.utc)


def _dt(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def days_until(expiry, now=None):
    """Whole days until `expiry` (aware). None if expiry is unknown/unavailable.
    Uses calendar-day flooring so a cert expiring in 2h today reads as 0 days,
    not a misleading '1'."""
    d = _dt(expiry)
    if d is None:
        return None
    delta = d - _now(now)
    return int(delta.total_seconds() // 86400)


def escalation(days):
    """Visual/severity tier from days remaining. None → 'unknown' (honest)."""
    if days is None:
        return "unknown"
    if days <= 3:
        return "critical"
    if days <= 14:
        return "warn"
    if days <= 30:
        return "notice"
    return "ok"


def ladder_crossing(prev_days, days):
    """The alert-ladder rung newly crossed downward since last check, or None.
    Change-only: fires once as the countdown passes each of 30/14/3."""
    if days is None:
        return None
    # Report the smallest (most urgent) rung newly crossed downward.
    for t in sorted(LADDER):  # 3, 14, 30
        if days <= t and (prev_days is None or prev_days > t):
            return t
    return None


def indexability_verdict(robots_ok, meta_noindex, header_noindex, sitemap_ok):
    """Roll the trio into per-check + overall. A page kept OUT of the index
    (noindex, or robots blocking everything) is Critical; a missing/broken
    sitemap is a lesser notice (it doesn't deindex an existing page).

    Any arg may be None → 'unknown' for that check (couldn't determine)."""
    checks = []

    def add(key, label, ok, fail_sev, ok_text, fail_text):
        if ok is None:
            checks.append({"key": key, "label": label, "status": "unknown", "text": "Couldn't check"})
        elif ok:
            checks.append({"key": key, "label": label, "status": "ok", "text": ok_text})
        else:
            checks.append({"key": key, "label": label, "status": fail_sev, "text": fail_text})

    add("robots", "robots.txt", robots_ok, "critical",
        "robots.txt currently allows search engines", "robots.txt is blocking all crawlers")
    noindex = None if (meta_noindex is None and header_noindex is None) else bool(meta_noindex or header_noindex)
    add("noindex", "Index directive", (None if noindex is None else not noindex), "critical",
        "Homepage is indexable (no noindex)", "Homepage carries a noindex directive")
    add("sitemap", "Sitemap", sitemap_ok, "notice",
        "Sitemap returns 200 and parses", "Sitemap is missing or won't parse")

    order = {"critical": 0, "warn": 1, "notice": 2, "unknown": 3, "ok": 4}
    overall = min((c["status"] for c in checks), key=lambda s: order[s])
    return {"overall": overall, "checks": checks}


def downtime_state(pings):
    """`pings` newest-first list of bools (True=up). Down only after 2
    consecutive failures (a single blip is not an outage)."""
    if not pings or len(pings) < 2:
        return False
    return pings[0] is False and pings[1] is False


def uptime_pct(pings):
    """Rolling uptime % over the supplied ping window. None if no pings."""
    vals = [p for p in (pings or []) if p is not None]
    if not vals:
        return None
    up = sum(1 for p in vals if p)
    return round(up / len(vals) * 100, 2)


# ─── Network probes (best-effort; failures surface honestly as unknown) ──────
async def check_ssl(host, port=443, timeout=8):
    """(expiry_iso|None, issuer|None). None expiry means we couldn't read it."""
    import asyncio
    import ssl

    def _probe():
        import socket
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ss:
                cert = ss.getpeercert()
        not_after = cert.get("notAfter")
        exp = None
        if not_after:
            dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            exp = dt.isoformat()
        issuer = ""
        for part in cert.get("issuer", ()):
            for k, v in part:
                if k == "organizationName":
                    issuer = v
        return exp, issuer or None

    try:
        return await asyncio.to_thread(_probe)
    except Exception:
        return None, None


async def check_domain_expiry(domain, client=None):
    """Domain expiry via RDAP. None when the TLD/registry hides it — shown as
    'unavailable', never faked."""
    import httpx
    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=10, follow_redirects=True)
    try:
        r = await client.get(f"https://rdap.org/domain/{domain}")
        if r.status_code != 200:
            return None
        data = r.json()
        for ev in data.get("events", []):
            if ev.get("eventAction") == "expiration":
                d = _dt(ev.get("eventDate"))
                return d.isoformat() if d else None
        return None
    except Exception:
        return None
    finally:
        if own:
            await client.aclose()


async def check_indexability(base_url, client=None):
    """(robots_ok, meta_noindex, header_noindex, sitemap_ok) — any may be None."""
    import re
    import httpx
    from urllib.parse import urljoin

    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=12, follow_redirects=True,
                                   headers={"User-Agent": "LinkSpyBot/1.0"})
    robots_ok = meta_noindex = header_noindex = sitemap_ok = None
    try:
        # robots.txt — blocking-all = "User-agent: *" then "Disallow: /"
        try:
            rr = await client.get(urljoin(base_url, "/robots.txt"))
            if rr.status_code == 200:
                body = rr.text.lower()
                robots_ok = not re.search(r"user-agent:\s*\*\s*(?:#.*\n|\n)*\s*disallow:\s*/\s*$",
                                          body, re.MULTILINE)
            else:
                robots_ok = True  # no robots.txt = nothing blocked
        except Exception:
            robots_ok = None
        # homepage noindex — meta tag AND X-Robots-Tag header
        try:
            hr = await client.get(base_url)
            header_noindex = "noindex" in (hr.headers.get("x-robots-tag", "").lower())
            meta_noindex = bool(re.search(r'<meta[^>]+name=["\']robots["\'][^>]*content=["\'][^"\']*noindex',
                                          hr.text, re.IGNORECASE))
        except Exception:
            meta_noindex = header_noindex = None
        # sitemap
        try:
            sr = await client.get(urljoin(base_url, "/sitemap.xml"))
            sitemap_ok = sr.status_code == 200 and ("<urlset" in sr.text or "<sitemapindex" in sr.text)
        except Exception:
            sitemap_ok = None
        return robots_ok, meta_noindex, header_noindex, sitemap_ok
    finally:
        if own:
            await client.aclose()


async def ping(url, client=None, timeout=8):
    """True if the site answers a HEAD (or GET fallback) with < 500."""
    import httpx
    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    try:
        try:
            r = await client.head(url)
            if r.status_code >= 400:
                r = await client.get(url)
        except httpx.HTTPError:
            r = await client.get(url)
        return r.status_code < 500
    except Exception:
        return False
    finally:
        if own:
            await client.aclose()


def summarize_sentinel(status, pings, now=None):
    """Build the guard-cards payload from a stored status row + recent pings.
    Pure. `status` carries ssl_expiry/ssl_issuer/domain_expiry/robots_ok/
    meta_noindex/header_noindex/sitemap_ok/last_checked_at."""
    status = status or {}
    ssl_days = days_until(status.get("ssl_expiry"), now)
    dom_days = days_until(status.get("domain_expiry"), now)
    idx = indexability_verdict(status.get("robots_ok"), status.get("meta_noindex"),
                               status.get("header_noindex"), status.get("sitemap_ok"))
    up_pct = uptime_pct(pings)
    down = downtime_state(pings)

    cards = [
        {"key": "ssl", "label": "SSL", "days": ssl_days, "escalation": escalation(ssl_days),
         "fact": (f"{ssl_days} days" if ssl_days is not None else "unavailable"),
         "detail": status.get("ssl_issuer")},
        {"key": "domain", "label": "Domain", "days": dom_days, "escalation": escalation(dom_days),
         "fact": (f"{dom_days} days" if dom_days is not None else "unavailable"), "detail": None},
        {"key": "index", "label": "Search visibility", "days": None, "escalation": idx["overall"],
         "fact": ("Indexable" if idx["overall"] == "ok" else
                  "Unknown" if idx["overall"] == "unknown" else "At risk"),
         "checks": idx["checks"]},
        {"key": "uptime", "label": "Uptime", "days": None,
         "escalation": "critical" if down else ("ok" if up_pct is not None else "unknown"),
         "fact": (f"{up_pct}%" if up_pct is not None else "—"), "detail": "30-day"},
    ]
    # Proximity = prominence: the most urgent card sorts first.
    rank = {"critical": 0, "warn": 1, "notice": 2, "unknown": 3, "ok": 4}
    cards.sort(key=lambda c: rank.get(c["escalation"], 4))

    worst = min((c["escalation"] for c in cards), key=lambda s: rank.get(s, 4))
    return {
        "cards": cards,
        "worst": worst,
        "all_clear": worst in ("ok",),
        "last_checked": status.get("last_checked_at"),
        "uptime_pct": up_pct,
        "down": down,
    }


# ─── Orchestration (network + storage; injected notify keeps it testable) ────
async def run_sentinel_for_site(site, notify=None, client=None):
    """One full sentinel pass for a site: SSL + domain + indexability. Updates
    stored status, fires change-only ladder alerts + indexability-critical."""
    from urllib.parse import urlparse
    from database import get_sentinel_status, upsert_sentinel_status

    url = site.get("url") or ""
    host = urlparse(url if "://" in url else "https://" + url).hostname
    if not host:
        return {"skipped": True}
    prev = await get_sentinel_status(site["id"]) or {}

    ssl_exp, issuer = await check_ssl(host)
    dom_exp = await check_domain_expiry(host, client=client)
    robots_ok, meta_ni, header_ni, sitemap_ok = await check_indexability(url, client=client)
    ssl_days, dom_days = days_until(ssl_exp), days_until(dom_exp)

    await upsert_sentinel_status(site["id"], {
        "ssl_expiry": ssl_exp, "ssl_issuer": issuer, "domain_expiry": dom_exp,
        "robots_ok": robots_ok, "meta_noindex": meta_ni, "header_noindex": header_ni,
        "sitemap_ok": sitemap_ok, "prev_ssl_days": ssl_days, "prev_domain_days": dom_days,
        "last_checked_at": _now().isoformat(),
    })

    alerts = []
    for label, prev_key, days in (("SSL certificate", "prev_ssl_days", ssl_days),
                                  ("Domain registration", "prev_domain_days", dom_days)):
        rung = ladder_crossing(prev.get(prev_key), days)
        if rung is not None:
            urgency = ":rotating_light:" if rung <= 3 else ":warning:"
            alerts.append(f"{urgency} *{label} expires in {days} days* — {host}")
    # Indexability critical, change-only (fire when it flips into a bad state).
    idx = indexability_verdict(robots_ok, meta_ni, header_ni, sitemap_ok)
    prev_idx = indexability_verdict(prev.get("robots_ok"), prev.get("meta_noindex"),
                                    prev.get("header_noindex"), prev.get("sitemap_ok"))
    if idx["overall"] == "critical" and prev_idx["overall"] != "critical":
        bad = next((c for c in idx["checks"] if c["status"] == "critical"), None)
        alerts.append(f":rotating_light: *Search visibility at risk* — {bad['text'] if bad else 'indexability'} · {host}")

    if notify:
        for a in alerts:
            try:
                await notify(a)
            except Exception:
                pass
    return {"ssl_days": ssl_days, "domain_days": dom_days, "index": idx["overall"], "alerts": len(alerts)}


async def run_uptime_for_site(site, notify=None, client=None):
    """One HEAD ping; opens an incident after 2 consecutive fails, closes +
    notifies on recovery."""
    from database import add_uptime_ping, recent_pings, open_incident, close_incident
    from urllib.parse import urlparse

    url = site.get("url") or ""
    host = urlparse(url if "://" in url else "https://" + url).hostname or url
    up = await ping(url if "://" in url else "https://" + url, client=client)
    await add_uptime_ping(site["id"], up)
    pings = await recent_pings(site["id"], limit=3)
    if downtime_state(pings):
        await open_incident(site["id"])
        if notify:
            try:
                await notify(f":rotating_light: *Site down* — {host} failed two consecutive checks")
            except Exception:
                pass
    elif up:
        if await close_incident(site["id"]) and notify:
            try:
                await notify(f":white_check_mark: *Back up* — {host} recovered")
            except Exception:
                pass
    return up


async def run_sentinel_all(notify=None):
    import httpx
    from database import all_sites_min
    sites = await all_sites_min()
    n = 0
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        for s in sites:
            try:
                await run_sentinel_for_site(s, notify=notify, client=client)
                n += 1
            except Exception:
                pass
    return {"checked": n}


async def run_uptime_all(notify=None):
    import httpx
    from database import all_sites_min
    sites = await all_sites_min()
    n = 0
    async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
        for s in sites:
            try:
                await run_uptime_for_site(s, notify=notify, client=client)
                n += 1
            except Exception:
                pass
    return {"pinged": n}
