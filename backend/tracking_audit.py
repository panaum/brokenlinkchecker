"""
Tracking & pixel integrity audit — passive, observation only.

Rides on the same rendered-DOM pass as the form audit. It reads the page's
tracking tags out of the already-rendered HTML (GTM/GA4/Meta/LinkedIn/TikTok)
and reports integrity problems in plain language a client understands:

  - the same pixel loaded twice        -> conversions double-counted
  - a form with no tracking at all      -> those conversions are invisible
  - UTMs dropped across a redirect       -> ad attribution lost
  - a thank-you page with no event       -> the sale is not being recorded

NOTHING here is ever "broken". A missing or mis-fired pixel is a marketing
integrity problem, not a dead link — the client's site still works. Every
finding lands in `unverifiable` with a Tracking category, so it shows up and
diffs like any other finding but never turns a report red, never dents the
health score, and never fires a monitoring alert. Severity is carried by
`priority`, not by a red bucket.

Extraction works on the rendered BeautifulSoup, so it is testable from an HTML
string with no browser.
"""
import re
from urllib.parse import urlparse, parse_qs

from models import LinkResult

CATEGORY = "Tracking"
RESOURCE = "tracking"

# ─── vendor id patterns ──────────────────────────────────────────────────────
# Read out of <script src> query strings and inline <script> text. Deterministic
# and traceable — no inference, no LLM.
_UA_RE = re.compile(r"\bUA-\d{4,}-\d+\b")            # legacy Universal Analytics
_META_HOST_RE = re.compile(r"connect\.facebook\.net/[^'\"]+/fbevents\.js")
_LINKEDIN_ID_RE = re.compile(r"_linkedin_partner_id\s*=\s*['\"](\d+)['\"]")
_LINKEDIN_HOST_RE = re.compile(r"snap\.licdn\.com")
_TIKTOK_ID_RE = re.compile(r"ttq\.load\(\s*['\"]([A-Z0-9]+)['\"]")
_TIKTOK_HOST_RE = re.compile(r"analytics\.tiktok\.com")

# A conversion actually being recorded, not just the library being present.
_EVENT_RE = re.compile(
    r"gtag\(\s*['\"]event['\"]"
    r"|fbq\(\s*['\"]track['\"]"
    r"|dataLayer\.push\(\s*\{[^}]*['\"]event['\"]"
    r"|ttq\.track\(",
    re.I,
)

# A thank-you / conversion page: where the event most needs to fire.
_THANKYOU_RE = re.compile(r"(thank|thankyou|thank-you|confirm|success|order-complete|receipt)", re.I)

# UTM and paid-click attribution params. If these start a redirect but are gone
# by the end, the campaign that paid for the click loses its attribution.
_ATTRIBUTION_PARAMS = (
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "msclkid", "ttclid", "li_fat_id",
)


# A placeholder from an un-filled template, never a real property. Flagging it —
# or counting it toward a duplicate — would be a false alarm.
_PLACEHOLDER_RE = re.compile(r"X{4,}", re.I)


def _is_placeholder(ident: str) -> bool:
    return bool(_PLACEHOLDER_RE.search(ident or ""))


# Duplicate detection counts INITIALISATION CALLS, which live in inline script:
#   GTM bootstrap  ...'GTM-XXXX')
#   GA4 config     gtag('config','G-XXXX')
#   Meta init      fbq('init','1234')
# NOT the library src (gtm.js?id=, gtag/js?id=) — one correct install injects
# that src itself, so counting it flags every proper install as a duplicate.
# And <noscript> is excluded: it is a fallback, never an active load.
_GTM_INIT_RE = re.compile(r"['\"](GTM-[A-Z0-9]{4,})['\"]")
_GA4_INIT_RE = re.compile(r"gtag\(\s*['\"]config['\"]\s*,\s*['\"](G-[A-Z0-9]{6,})['\"]")
_META_INIT_RE = re.compile(r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{6,})['\"]")
# Src-based discovery: proves a vendor is present even when the init is minified
# away or server-side. Used for the inventory list, never for dup counting.
_GTM_SRC_RE = re.compile(r"gtm\.js\?id=(GTM-[A-Z0-9]{4,})")
_GA4_SRC_RE = re.compile(r"gtag/js\?id=(G-[A-Z0-9]{6,})")


def _script_material(soup) -> tuple:
    """(script srcs, inline text). <noscript> is stripped: it is a fallback,
    never an active tag load, and counting it double-counts every GTM."""
    srcs, inline = [], []
    for tag in soup.find_all("script"):
        src = tag.get("src")
        if src:
            srcs.append(src)
        else:
            text = tag.string or tag.get_text()
            if text:
                inline.append(text)
    return srcs, "\n".join(inline)


def _init_counts(init_re, inline) -> dict:
    """id -> number of initialisation calls in inline script. Placeholders out."""
    counts = {}
    for ident in init_re.findall(inline):
        if ident and not _is_placeholder(ident):
            counts[ident] = counts.get(ident, 0) + 1
    return counts


def extract_tracking(soup) -> dict:
    """The tracking inventory of one rendered page. No network, no browser."""
    srcs, inline = _script_material(soup)
    src_blob = "\n".join(srcs)
    blob = inline + "\n" + src_blob

    # Init counts (inline only) drive duplicate detection.
    gtm_loads = _init_counts(_GTM_INIT_RE, inline)
    ga4_loads = _init_counts(_GA4_INIT_RE, inline)
    meta_loads = _init_counts(_META_INIT_RE, inline)
    ua = [i for i in _UA_RE.findall(blob) if not _is_placeholder(i)]

    # Discovery (which ids exist) unions inits with src-detected ids.
    gtm = sorted(set(gtm_loads) | {i for i in _GTM_SRC_RE.findall(src_blob)
                                   if not _is_placeholder(i)})
    ga4 = sorted(set(ga4_loads) | {i for i in _GA4_SRC_RE.findall(src_blob)
                                   if not _is_placeholder(i)})
    meta = list(meta_loads)
    if not meta and _META_HOST_RE.search(blob):
        meta = ["(present, id not readable)"]
    linkedin = [i for i in _LINKEDIN_ID_RE.findall(blob) if not _is_placeholder(i)]
    if not linkedin and _LINKEDIN_HOST_RE.search(blob):
        linkedin = ["(present, id not readable)"]
    tiktok = [i for i in _TIKTOK_ID_RE.findall(blob) if not _is_placeholder(i)]
    if not tiktok and _TIKTOK_HOST_RE.search(blob):
        tiktok = ["(present, id not readable)"]

    has_gtag = "gtag(" in blob or "googletagmanager.com/gtag/js" in blob
    has_datalayer = "dataLayer" in blob
    has_event = bool(_EVENT_RE.search(blob))

    # (vendor, id, load_count) — duplicate detection reads the count, so a single
    # install (inline + noscript) is one load, and two bootstraps are two.
    load_counts = (
        [("GTM", i, n) for i, n in gtm_loads.items()]
        + [("GA4", i, n) for i, n in ga4_loads.items()]
        + [("Meta", i, n) for i, n in meta_loads.items()]
    )

    any_tracking = bool(
        gtm or ga4 or ua or meta or linkedin or tiktok or has_gtag or has_datalayer
    )

    return {
        "gtm": gtm, "ga4": ga4, "ua": ua, "meta_pixel": meta,
        "linkedin": linkedin, "tiktok": tiktok,
        "has_gtag": has_gtag, "has_datalayer": has_datalayer,
        "has_event": has_event,
        "load_counts": load_counts,
        "any_tracking": any_tracking,
    }


# ─── UTM survival, from the checker's redirect_chain ─────────────────────────
def _attribution_params(url: str) -> set:
    if not url:
        return set()
    query = parse_qs(urlparse(url).query)
    return {k for k in query if k.lower() in _ATTRIBUTION_PARAMS}


def dropped_attribution(redirect_chain) -> set:
    """Attribution params present on the first hop but gone by the last.

    Uses the checker's existing redirect_chain — no new request.
    """
    if not redirect_chain or len(redirect_chain) < 2:
        return set()
    start = _attribution_params(redirect_chain[0].get("url", ""))
    end = _attribution_params(redirect_chain[-1].get("url", ""))
    return start - end


# ─── classification ──────────────────────────────────────────────────────────
def _has_lead_form(forms) -> bool:
    """A form a visitor submits something through — the thing whose conversion
    the tracking is supposed to record. Mirrors the form audit's notion."""
    for form in forms or []:
        typable = [
            f for f in (form.get("fields") or [])
            if f.get("type") not in ("hidden", "submit", "button", "image", "reset")
        ]
        if typable:
            return True
    return False


def _finding(page_url: str, anchor: str, reason: str, priority: str,
             identity: str, confidence: str = "high") -> LinkResult:
    """A tracking finding as a LinkResult. Never `broken` — unverifiable, so it
    diffs and shows without turning a report red or denting the health score."""
    return LinkResult(
        url=f"{page_url}#tracking-{identity}",
        source_element="script",
        anchor_text=anchor,
        category=CATEGORY,
        is_external=False,
        zones=[CATEGORY],
        link_kind=RESOURCE,
        resource_type=RESOURCE,
        priority=priority,
        bucket="unverifiable",
        confidence=confidence,
        reason=reason,
        label="tracking",
        status_code=None,
        response_ms=0,
    )


def _duplicate_ids(load_counts) -> list:
    """(vendor, id) pairs ACTIVELY LOADED more than once — a genuine double
    install, not a single install's inline+noscript pair."""
    return [(vendor, ident) for vendor, ident, n in (load_counts or []) if n > 1]


def audit_tracking(signals: dict, results, page_url: str,
                   expected: dict = None) -> list:
    """Tracking-integrity findings for one page. Passive, never `broken`.

    `results` are the already-checked LinkResults (with redirect_chain), so UTM
    survival costs no new request. `expected` optionally holds the site's own
    GA4 / Meta ids for a mismatch check.
    """
    signals = signals or {}
    tracking = signals.get("tracking") or {}
    forms = signals.get("forms") or []
    findings = []

    # 1. Duplicate ids — double counting.
    for vendor, ident in _duplicate_ids(tracking.get("load_counts") or []):
        findings.append(_finding(
            page_url, f"{vendor} {ident}",
            f"{vendor} tag {ident} is loaded more than once on this page — "
            f"conversions and pageviews may be double-counted, inflating your "
            f"reports.",
            priority="medium", identity=f"dup-{vendor}-{ident}"))

    # 2. A form, but no tracking at all — conversions invisible.
    if _has_lead_form(forms) and not tracking.get("any_tracking"):
        findings.append(_finding(
            page_url, "Form with no tracking",
            "This page has a form but no analytics or pixel loaded — when a "
            "visitor submits it, nothing records the conversion. You cannot see "
            "which campaigns are producing leads here.",
            priority="high", identity="form-no-tracking"))

    # 3. UTM / click-id survival across redirects.
    for r in results or []:
        chain = getattr(r, "redirect_chain", None) or (
            r.get("redirect_chain") if isinstance(r, dict) else None)
        dropped = dropped_attribution(chain)
        if dropped:
            url = getattr(r, "url", None) or (r.get("url") if isinstance(r, dict) else "")
            findings.append(_finding(
                page_url, f"Attribution dropped: {url}",
                f"A link with campaign tracking ({', '.join(sorted(dropped))}) "
                f"redirects to a URL where those parameters are gone. The ad "
                f"attribution for that click is being lost.",
                priority="high", identity=f"utm-{abs(hash(url)) % 10**8}"))

    # 4. A thank-you / conversion page with no event firing — HIGH.
    if _THANKYOU_RE.search(page_url or "") and not tracking.get("has_event"):
        findings.append(_finding(
            page_url, "Conversion page not recording",
            "This looks like a thank-you / confirmation page, but no conversion "
            "event fires on it. Sales or sign-ups completing here are probably "
            "not being counted — your reported conversion rate is too low.",
            priority="high", identity="thankyou-no-event"))

    # 5. Expected-id mismatch, if the site stored its ids.
    if expected:
        findings.extend(_mismatch_findings(page_url, tracking, expected))

    return findings


def _mismatch_findings(page_url: str, tracking: dict, expected: dict) -> list:
    """Flag when a page carries a tracking id that is not the site's own — a
    common sign of a mis-pasted snippet sending data to the wrong property."""
    out = []
    checks = [
        ("ga4", "GA4 measurement ID", expected.get("ga4")),
        ("meta_pixel", "Meta Pixel ID", expected.get("meta_pixel")),
        ("gtm", "GTM container", expected.get("gtm")),
    ]
    for key, label, want in checks:
        if not want:
            continue
        seen = [i for i in (tracking.get(key) or []) if not i.startswith("(")]
        if seen and want not in seen:
            out.append(_finding(
                page_url, f"Unexpected {label}",
                f"This page's {label} is {', '.join(seen)}, not your configured "
                f"{want}. Data from this page may be going to the wrong account.",
                priority="high", identity=f"mismatch-{key}"))
    return out
