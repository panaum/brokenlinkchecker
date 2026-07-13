"""Consent-relevance classification — legal-adjacent, so the table itself is
auditable: every class carries PROVENANCE (why this host is classed this way)
and the table is VERSIONED.

This tool OBSERVES AND RECORDS technical behavior. Classes describe what a
request IS technically, not any legal conclusion about it.

Reuses the existing host→category table (integration_audit.classify_host); this
module adds the consent-relevance dimension on top.
"""
from integration_audit import (classify_host, ANALYTICS, ADVERTISING, TAG_MANAGEMENT,
                               CRM_FORMS, CHAT_SUPPORT, PAYMENT, SCHEDULING, CONTENT_MEDIA,
                               FONTS_CDN, OTHER)

CLASSIFICATION_VERSION = 1

# The four consent-relevance classes.
ESSENTIAL = "essential"          # own-domain, CDN, security, fonts, payment rails
ANALYTICS_C = "analytics"        # measurement — non-essential, consent-relevant
ADTECH = "advertising-adtech"    # the CPRA "sharing" class — Meta/Google Ads/TikTok/LinkedIn
FUNCTIONAL = "functional"        # chat, scheduling, embedded media — enhances, not tracking
UNKNOWN = "unknown"              # unclassifiable third party → a declared limitation, never a verdict

# Category → (consent class, provenance). Provenance is the audit trail for the
# table itself: it states the reasoning, not a legal determination.
_CATEGORY_TO_CLASS = {
    ADVERTISING:    (ADTECH, "Advertising/pixel host — the CPRA 'sharing' class; sends data usable for cross-context behavioural advertising."),
    ANALYTICS:      (ANALYTICS_C, "Analytics/measurement host — non-essential under UK PECR; consent-relevant."),
    TAG_MANAGEMENT: (ANALYTICS_C, "Tag manager — a loader for non-essential tags; treated as consent-relevant because it commonly injects analytics/adtech."),
    CRM_FORMS:      (FUNCTIONAL, "CRM/forms host — supports a user-initiated function (form submission)."),
    CHAT_SUPPORT:   (FUNCTIONAL, "Live-chat/support widget — a functional enhancement."),
    SCHEDULING:     (FUNCTIONAL, "Scheduling widget — a functional enhancement."),
    CONTENT_MEDIA:  (FUNCTIONAL, "Embedded media (video/audio) — functional; may set cookies once played."),
    PAYMENT:        (ESSENTIAL, "Payment processor — strictly necessary for a transaction the user initiates."),
    FONTS_CDN:      (ESSENTIAL, "Fonts/CDN/library host — infrastructure, strictly necessary for the page to render."),
    OTHER:          (UNKNOWN, "Unrecognised third-party host — cannot be classified from the host alone; recorded as a limitation, not judged."),
}

# The adtech "sharing" hosts get named provenance where we can, for the ledger's
# reproducibility. (Substring → the specific vendor note.)
_ADTECH_VENDOR_NOTES = (
    ("facebook", "Meta (Facebook) advertising pixel."),
    ("doubleclick", "Google DoubleClick / Google Ads."),
    ("googleadservices", "Google Ads conversion."),
    ("googlesyndication", "Google ad serving."),
    ("tiktok", "TikTok advertising pixel."),
    ("licdn", "LinkedIn Insight / advertising."),
    ("ads.linkedin", "LinkedIn advertising."),
    ("bing", "Microsoft/Bing advertising."),
    ("snap", "Snap advertising pixel."),
)


def consent_class(host, url="", site_host=""):
    """Return {class, provenance, category, source}. First-party (own-domain)
    requests are ESSENTIAL by definition; everything else is judged by host."""
    h = (host or "").lower()
    sh = (site_host or "").lower().replace("www.", "")
    if sh and (h == sh or h.endswith("." + sh)):
        return {"class": ESSENTIAL, "provenance": "First-party host (same registrable domain as the site).",
                "category": "First-party", "source": "own-domain"}
    category = classify_host(h, url)
    cls, prov = _CATEGORY_TO_CLASS.get(category, (UNKNOWN, _CATEGORY_TO_CLASS[OTHER][1]))
    if cls == ADTECH:
        for marker, note in _ADTECH_VENDOR_NOTES:
            if marker in f"{h} {url}".lower():
                prov = note + " " + prov
                break
    return {"class": cls, "provenance": prov, "category": category, "source": "host-table"}


def is_non_essential(cls):
    return cls in (ANALYTICS_C, ADTECH, FUNCTIONAL)


def classification_table():
    """The full table, exported for the ledger + attestation appendix + audit."""
    return {"version": CLASSIFICATION_VERSION,
            "rules": [{"category": cat, "class": cls, "provenance": prov}
                      for cat, (cls, prov) in _CATEGORY_TO_CLASS.items()]}
