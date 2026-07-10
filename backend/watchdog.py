"""
Third-party watchdog — cross-site shared-dependency outage detection.

Every site LinkSpy scans loads third-party code: a GTM container, a Calendly
embed, a HubSpot form script, an Intercom widget. When one of those hosts goes
down it breaks the same thing on every client at once — and the client whose
site "suddenly stopped taking bookings" has no idea the cause is Calendly, not
them.

This module inventories the external hosts each scan sees, and when a shared
host is failing across sites it raises ONE alert naming every affected client —
not one alert per site, and not the same outage again within a day.

Two disciplines carried from the rest of the product:

  A THIRD PARTY'S OUTAGE IS NOT THE CLIENT'S FAULT. A dead Calendly is a dead
  Calendly. For the link verdict it is `unverifiable` (their server, not the
  client's site), so it never turns a client's report red. The watchdog still
  fires, because a dead embed still breaks functionality.

  ONE ALERT, NOT N. A host down on ten sites is one outage. Ten Slack messages
  is noise; one message listing ten clients is signal. And the same outage is
  not re-announced within the dedupe window.

Pure logic with injected I/O — inventory, aggregation and dedupe are all tested
without a database or network.
"""
from urllib.parse import urlparse


# Resource kinds whose host is a third-party dependency worth watching. A dead
# script or embed breaks behaviour; a dead image is cosmetic and noisier, so it
# is left out of the watchdog.
_WATCHED_RESOURCE_TYPES = frozenset({"script", "iframe", "form_action"})

# Known embed/widget/analytics hosts — a failure here is unambiguously "their
# server". Shared with the form audit's embed check rather than redefined.
KNOWN_THIRD_PARTY = (
    "hs-scripts.com", "hsforms.net", "js.hsforms.net", "hubspot",
    "embed.typeform.com", "form.jotform", "jotform", "calendly.com",
    "paperform", "formstack", "wufoo", "gravityforms", "marketo", "munchkin",
    "pardot", "leadconnectorhq", "msgsndr", "intercom", "drift.com",
    "googletagmanager.com", "google-analytics.com", "connect.facebook.net",
    "snap.licdn.com", "analytics.tiktok.com", "widget", "cdn.", "js.stripe.com",
    "player.vimeo.com", "youtube.com/embed", "maps.googleapis.com",
)

# A resource verdict that means the host itself failed to serve — its server,
# a DNS death, or a timeout. These fire the watchdog. A 401/403/429 is anti-bot
# noise, not an outage, and is ignored.
_DOWN_BUCKETS = frozenset({"broken", "error", "timeout"})
_DOWN_STATUSES = frozenset({404, 410, 500, 502, 503, 504, 522, 523, 525})

DEFAULT_DEDUPE_HOURS = 24


def _get(obj, field, default=None):
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def is_third_party(url: str, page_url: str) -> bool:
    """A host on a different registered site than the page, or a known widget."""
    host = _host_of(url)
    if not host:
        return False
    if any(marker in host or marker in (url or "").lower() for marker in KNOWN_THIRD_PARTY):
        return True
    page_host = _host_of(page_url)
    if not page_host:
        return host != ""
    # Different registrable-ish domain: compare the last two labels.
    return _registrable(host) != _registrable(page_host)


def _registrable(host: str) -> str:
    parts = (host or "").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def host_failed(result) -> bool:
    """True when this checked resource shows its HOST failing to serve.

    Only server-level failure counts — not a 403/429 bot-block, which says
    nothing about whether the host is up.
    """
    bucket = _get(result, "bucket")
    status = _get(result, "status_code")
    if status in _DOWN_STATUSES:
        return True
    if status is None and bucket in _DOWN_BUCKETS:
        return True   # DNS-dead / connection refused / timeout
    if bucket in _DOWN_BUCKETS and (status is None or status >= 500 or status in (404, 410)):
        return True
    return False


# ─── inventory ───────────────────────────────────────────────────────────────
def inventory_hosts(results, page_url: str) -> list:
    """One record per third-party host on this page: worst status wins.

    [{host, resource_type, status, sample_url, down}] — the raw material the DB
    upserts and the aggregator groups across sites.
    """
    by_host = {}
    for r in results or []:
        rtype = _get(r, "resource_type")
        url = _get(r, "url") or ""
        if rtype not in _WATCHED_RESOURCE_TYPES:
            continue
        if not is_third_party(url, page_url):
            continue
        host = _host_of(url)
        if not host:
            continue
        down = host_failed(r)
        prev = by_host.get(host)
        # Worst status wins: a host down on any resource is down.
        if prev is None or (down and not prev["down"]):
            by_host[host] = {
                "host": host,
                "resource_type": rtype,
                "status": _get(r, "status_code"),
                "sample_url": url,
                "down": down,
            }
    return list(by_host.values())


# ─── the link-verdict demotion (item 3) ──────────────────────────────────────
def demote_third_party_failures(results, page_url: str) -> int:
    """A third-party script/iframe whose HOST failed is not the client's broken
    link. Demote it to `unverifiable` so it never turns their report red — the
    watchdog is what raises the outage. Mutates in place; returns the count.
    """
    demoted = 0
    for r in results or []:
        if _get(r, "resource_type") not in _WATCHED_RESOURCE_TYPES:
            continue
        if _get(r, "bucket") not in _DOWN_BUCKETS:
            continue
        url = _get(r, "url") or ""
        if not is_third_party(url, page_url):
            continue
        if not host_failed(r):
            continue
        host = _host_of(url)
        r.bucket = "unverifiable"
        r.label = "blocked"
        r.priority = None
        r.error = None
        r.reason = (
            f"{host} is a third-party service and its server is not responding. "
            f"This breaks the embed, but it is their outage, not a broken link "
            f"on your site — we flag it separately in the watchdog."
        )
        demoted += 1
    return demoted


# ─── cross-site aggregation ──────────────────────────────────────────────────
def aggregate_outages(inventory_rows) -> list:
    """Group DOWN hosts across sites into one outage each.

    `inventory_rows` is the stored inventory across all sites, each row at least
    {host, site_id, down, client, site_url, status}. Returns one Outage per host
    that is down somewhere, naming every affected site — the shape an alert and
    the /api/watchdog/hosts endpoint both use.
    """
    outages = {}
    for row in inventory_rows or []:
        if not _get(row, "down"):
            continue
        host = _get(row, "host")
        if not host:
            continue
        entry = outages.setdefault(host, {
            "host": host, "status": _get(row, "status"),
            "resource_type": _get(row, "resource_type"), "sites": [],
        })
        entry["sites"].append({
            "site_id": _get(row, "site_id"),
            "site_url": _get(row, "site_url"),
            "client": _get(row, "client") or _get(row, "site_url"),
        })
    # Stable order: worst blast radius first.
    return sorted(outages.values(), key=lambda o: (-len(o["sites"]), o["host"]))


# ─── dedupe within the window ────────────────────────────────────────────────
def outages_to_alert(outages, recently_alerted, now_ts: float,
                     window_hours: int = DEFAULT_DEDUPE_HOURS) -> list:
    """Drop any outage whose host was already alerted inside the window.

    `recently_alerted` maps host -> last-alerted epoch seconds. `now_ts` is
    passed in (never read from the clock here) so this stays a pure function.
    """
    window = window_hours * 3600
    fresh = []
    for outage in outages or []:
        last = (recently_alerted or {}).get(outage["host"])
        if last is not None and (now_ts - last) < window:
            continue
        fresh.append(outage)
    return fresh


def format_outage_alert(outage) -> str:
    """One plain-language line naming every affected client. No jargon."""
    n = len(outage["sites"])
    clients = ", ".join(sorted({s["client"] for s in outage["sites"] if s.get("client")}))
    status = outage.get("status")
    detail = f"returning {status}" if status else "not responding"
    noun = "site" if n == 1 else "sites"
    return (f"{outage['host']} is {detail} — this breaks an embed on {n} "
            f"{noun}: {clients}. It is the provider's outage, not the clients' "
            f"sites.")


# ─── orchestration (injected I/O) ────────────────────────────────────────────
async def run_watchdog(*, get_inventory, get_recently_alerted, record_alert,
                       notify, now_ts: float, window_hours: int = DEFAULT_DEDUPE_HOURS) -> dict:
    """Aggregate current outages, drop ones already alerted, fire ONE alert each.

    Injected I/O:
      get_inventory()               -> rows across all sites
      get_recently_alerted()        -> {host: last_alerted_epoch}
      record_alert(host, now_ts)    -> persist that we alerted
      notify(text, outage)          -> the existing Slack sender
    """
    inventory = await get_inventory()
    outages = aggregate_outages(inventory)
    recent = await get_recently_alerted()
    fresh = outages_to_alert(outages, recent, now_ts, window_hours)

    for outage in fresh:
        await notify(format_outage_alert(outage), outage)
        await record_alert(outage["host"], now_ts)

    return {
        "outages": len(outages),
        "alerted": len(fresh),
        "suppressed": len(outages) - len(fresh),
    }
