"""
Per-page third-party integration inventory + health.

Every page a client ships loads other companies' code — GTM, a Calendly embed,
a HubSpot form script, Meta Pixel, a font CDN. This collects them per page,
says who they are, and whether each is actually loading.

Nothing here is a new detector. It REUSES:
  - tracking_audit.extract_tracking  -> the inline-snippet integrations (GTM/GA4/
    Meta/LinkedIn/TikTok) with their IDs, already init-counted and placeholder-
    filtered.
  - resources.collect_resources      -> the <script>/<iframe>/<link> resources,
    already health-checked by the scan's checker (so their verdict is reused).
  - watchdog.is_third_party/_registrable/_host_of -> host logic + first-party
    filter, identical to the global watchdog so the two agree.

The one thing added is a finer health mapping than the watchdog's binary
up/down: a 403/429/999 is a bot-block (status "unknown", never "down"), and a
timeout is "unresponsive", distinct from a real "down" (404/410/5xx/DNS).
"""
from urllib.parse import urlparse

from watchdog import _registrable, _host_of


def _is_third_party(url: str, page_url: str) -> bool:
    """A resource on a DIFFERENT registrable domain than the page.

    First-party wins: cdn.acme.com on acme.com is first-party, even though the
    watchdog's marker list would flag a bare "cdn." host. Same registrable
    domain (incl. www/other subdomains) is always excluded.
    """
    host = _host_of(url)
    page_host = _host_of(page_url)
    if not host or not page_host:
        return False
    return _registrable(host) != _registrable(page_host)


# ─── categories ──────────────────────────────────────────────────────────────
ANALYTICS = "Analytics"
ADVERTISING = "Advertising/Pixels"
TAG_MANAGEMENT = "Tag Management"
CRM_FORMS = "CRM/Forms"
CHAT_SUPPORT = "Chat/Support"
PAYMENT = "Payment"
SCHEDULING = "Scheduling"
CONTENT_MEDIA = "Content/Media"
FONTS_CDN = "Fonts/CDN"
OTHER = "Other"

# Registrable-domain (or host substring) → category. Substring match on the host
# so subdomains resolve (js.hs-scripts.com and hsforms.net both → CRM/Forms).
_CATEGORY_RULES = (
    (TAG_MANAGEMENT, ("googletagmanager.com", "tagmanager.google", "segment.com", "segment.io")),
    (ANALYTICS, ("google-analytics.com", "analytics.google.com", "mixpanel.com",
                 "amplitude.com", "heap.io", "hotjar.com", "hotjar.io", "clarity.ms",
                 "fullstory.com", "logrocket", "posthog", "matomo", "plausible.io",
                 "crazyegg.com", "heapanalytics.com", "leadinfo", "leadfeeder")),
    (ADVERTISING, ("connect.facebook.net", "facebook.com/tr", "facebook.net",
                   "doubleclick.net", "googleadservices.com", "googlesyndication.com",
                   "google.com/ads", "snap.licdn.com", "ads.linkedin.com",
                   "analytics.tiktok.com", "bat.bing.com", "ads-twitter.com",
                   "hsadspixel", "adroll.com", "criteo", "taboola", "outbrain")),
    (CRM_FORMS, ("hs-scripts.com", "hsforms.net", "hs-analytics.net", "hs-banner.com",
                 "hubspot", "js.hsforms.net", "marketo", "munchkin", "pardot",
                 "act-on.com", "eloqua", "salesforce", "formstack", "jotform",
                 "typeform.com", "wufoo", "gravityforms", "leadconnectorhq", "msgsndr")),
    (CHAT_SUPPORT, ("intercom.io", "intercom.com", "intercomcdn", "drift.com",
                    "driftt.com", "tawk.to", "zdassets.com", "zendesk", "crisp.chat",
                    "livechatinc", "tidio", "freshchat", "olark", "helpscout")),
    (PAYMENT, ("js.stripe.com", "checkout.stripe.com", "stripe.com", "paypal.com",
               "paypalobjects.com", "braintreegateway", "squareup.com", "razorpay.com",
               "checkout.com", "adyen.com")),
    (SCHEDULING, ("calendly.com", "assets.calendly", "acuityscheduling", "youcanbook.me",
                  "savvycal.com", "cal.com", "chilipiper")),
    (CONTENT_MEDIA, ("youtube.com", "youtube-nocookie.com", "ytimg.com", "vimeo.com",
                     "player.vimeo", "wistia", "cloudinary", "brightcove", "loom.com",
                     "spotify.com", "soundcloud")),
    (FONTS_CDN, ("fonts.googleapis.com", "fonts.gstatic.com", "use.typekit",
                 "use.fontawesome", "kit.fontawesome", "cdnjs.cloudflare.com",
                 "jsdelivr.net", "unpkg.com", "cdn.jsdelivr", "bootstrapcdn",
                 "gstatic.com", "jquery.com", "polyfill", "cdn.")),
)


def classify_host(host: str, url: str = "") -> str:
    """Registrable-domain → category. Unknown hosts are OTHER, never dropped."""
    hay = f"{host} {url}".lower()
    for category, markers in _CATEGORY_RULES:
        if any(m in hay for m in markers):
            return category
    return OTHER


# ─── the inline-snippet vendors (from tracking_audit) ────────────────────────
# id-list key -> (vendor label, host it loads from, injected library URL whose
# health stands in for the snippet's, and the CATEGORY by vendor — GA4 and GTM
# both load from googletagmanager.com, but GA4 is Analytics and GTM is Tag
# Management, so an inline snippet is categorized by vendor, not by host.
_INLINE_VENDORS = {
    "gtm":        ("GTM", "googletagmanager.com", "https://www.googletagmanager.com/gtm.js", TAG_MANAGEMENT),
    "ga4":        ("GA4", "www.googletagmanager.com", "https://www.googletagmanager.com/gtag/js", ANALYTICS),
    "ua":         ("Universal Analytics", "www.google-analytics.com", "https://www.google-analytics.com/analytics.js", ANALYTICS),
    "meta_pixel": ("Meta Pixel", "connect.facebook.net", "https://connect.facebook.net/en_US/fbevents.js", ADVERTISING),
    "linkedin":   ("LinkedIn Insight", "snap.licdn.com", "https://snap.licdn.com/li.lms-analytics/insight.min.js", ADVERTISING),
    "tiktok":     ("TikTok Pixel", "analytics.tiktok.com", "https://analytics.tiktok.com/i18n/pixel/events.js", ADVERTISING),
}


def _get(obj, field, default=None):
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


# ─── health mapping (finer than the watchdog's up/down) ──────────────────────
HEALTHY, DOWN, UNRESPONSIVE, UNKNOWN, CHECKING = (
    "healthy", "down", "unresponsive", "unknown", "checking")

_DOWN_STATUSES = frozenset({404, 410, 500, 502, 503, 504, 522, 523, 525, 526})
# A resource the target's server refuses/limits to bots — says nothing about it
# being down.
_BLOCKED_STATUSES = frozenset({401, 403, 405, 429, 999})


def resource_health(result) -> str:
    """Health of one checked resource. Burden of proof on 'down':
       2xx                         -> healthy
       404/410/5xx/DNS/refused     -> down
       timeout                     -> unresponsive
       401/403/405/429/999/blocked -> unknown (bot-blocked, not proof of down)
    """
    status = _get(result, "status_code")
    bucket = _get(result, "bucket")
    label = _get(result, "label")
    if status is not None and 200 <= status < 300:
        return HEALTHY
    if status in _DOWN_STATUSES:
        return DOWN
    if status in _BLOCKED_STATUSES or bucket in ("blocked", "unverifiable"):
        return UNKNOWN
    if status is None:
        # No status: a timeout is unresponsive; a DNS/refused failure is down.
        if label == "timeout" or bucket == "timeout":
            return UNRESPONSIVE
        if bucket in ("broken", "error"):
            return DOWN
        return UNKNOWN
    if status and status >= 400:
        return DOWN
    return UNKNOWN


# ─── detection (per page) ────────────────────────────────────────────────────
# Fetched third-party sub-resources we surface. A <link> stylesheet and a CSS
# url() are "script"-class fetched code/asset for the type enum; a media embed is
# iframe-class. form_action endpoints are a separate concern and excluded.
_RESOURCE_TYPES = {"script": "script", "iframe": "iframe",
                   "stylesheet": "script", "css_url": "script", "media": "iframe"}


def collect_integrations(results, signals: dict, page_url: str) -> list:
    """Every third-party integration on one page, with health.

    Reuses the checked `results` (resource verdicts) and `signals["tracking"]`
    (inline snippets). Returns a list of records:
      {host, resource_url, category, type, detected_id, health}
    Deduped per (host, resource_url, detected_id) within the page.
    """
    signals = signals or {}
    seen = set()
    out = []

    def emit(host, resource_url, rtype, detected_id, health, category=None):
        key = (host, resource_url, detected_id)
        if key in seen:
            return
        seen.add(key)
        out.append({
            "host": host,
            "resource_url": resource_url,
            "category": category or classify_host(host, resource_url),
            "type": rtype,
            "detected_id": detected_id,
            "health": health,
        })

    # 1. Fetched resources (script/iframe/link/media) — third party only, health
    #    reused from the scan's own verdict.
    for r in results or []:
        rtype = _RESOURCE_TYPES.get(_get(r, "resource_type"))
        if not rtype:
            continue
        url = _get(r, "url") or ""
        if not _is_third_party(url, page_url):
            continue
        host = _host_of(url)
        if not host:
            continue
        emit(host, url, rtype, None, resource_health(r))

    # 2. Inline-snippet integrations (GTM/GA4/Meta/…) from tracking_audit — the
    #    ID is shown; health borrows the injected library's verdict if the scan
    #    checked it, else "unknown".
    tracking = signals.get("tracking") or {}
    lib_health = {}   # injected-lib host -> health, from the resources above
    for rec in out:
        lib_health.setdefault(rec["host"], rec["health"])

    for key, (vendor, host, lib_url, category) in _INLINE_VENDORS.items():
        for ident in tracking.get(key) or []:
            detected = None if str(ident).startswith("(") else ident
            health = lib_health.get(host) or _lib_health_from_results(results, lib_url) or UNKNOWN
            emit(host, lib_url, "inline_snippet", detected, health, category=category)

    return out


def _lib_health_from_results(results, lib_url: str) -> str:
    """If a snippet's injected library was itself fetched during the scan, use
    that verdict. Matched by URL prefix (the src carries ?id=… query)."""
    base = lib_url.split("?", 1)[0]
    for r in results or []:
        u = (_get(r, "url") or "").split("?", 1)[0]
        if u == base:
            return resource_health(r)
    return ""


# ─── URLs that still need a health check (not covered by the scan) ───────────
def unchecked_resource_urls(integrations) -> list:
    """Resource URLs whose health is still unknown/checking and that have a
    fetchable http(s) URL — the background health task will GET these."""
    urls = []
    for rec in integrations or []:
        if rec["health"] in (UNKNOWN, CHECKING) and rec["resource_url"].startswith(("http://", "https://")):
            if rec["resource_url"] not in urls:
                urls.append(rec["resource_url"])
    return urls


def status_to_health(status_code, errored: bool = False) -> str:
    """Map a raw background-GET outcome to a health status (same rules)."""
    if errored or status_code is None:
        return UNRESPONSIVE if errored else UNKNOWN
    if 200 <= status_code < 300:
        return HEALTHY
    if status_code in _DOWN_STATUSES or status_code >= 500:
        return DOWN
    if status_code in _BLOCKED_STATUSES:
        return UNKNOWN
    if status_code >= 400:
        return DOWN
    return UNKNOWN
