"""CMP (consent-management platform) adapter table.

Named adapters for the common CMPs + a generic text heuristic. An UNKNOWN CMP is
never guessed at — the render engine records a declared limitation instead.

Selectors are Playwright-compatible. `detect` identifies the banner; `reject`
and `accept` are ordered candidate selectors (first that exists wins).
"""
import re

CMP_ADAPTERS = (
    {"vendor": "OneTrust",
     "detect": ["#onetrust-banner-sdk", "#onetrust-consent-sdk", ".onetrust-pc-dark-filter"],
     "reject": ["#onetrust-reject-all-handler", "button:has-text('Reject All')"],
     "accept": ["#onetrust-accept-btn-handler", "button:has-text('Accept All')"]},
    {"vendor": "Cookiebot",
     "detect": ["#CybotCookiebotDialog", "#CookiebotWidget"],
     "reject": ["#CybotCookiebotDialogBodyButtonDecline", "button:has-text('Decline')"],
     "accept": ["#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
                "#CybotCookiebotDialogBodyButtonAccept"]},
    {"vendor": "CookieYes",
     "detect": [".cky-consent-container", ".cky-modal", "[data-cky-tag='notice']"],
     "reject": [".cky-btn-reject", "[data-cky-tag='reject-button']"],
     "accept": [".cky-btn-accept", "[data-cky-tag='accept-button']"]},
    {"vendor": "Termly",
     "detect": ["#termly-code-snippet-support", ".termly-styles-root", "[data-testid='banner']"],
     "reject": ["[data-tid='banner-decline']", "button:has-text('Decline')", "button:has-text('Reject')"],
     "accept": ["[data-tid='banner-accept']", "button:has-text('Accept')"]},
    {"vendor": "HubSpot",
     "detect": ["#hs-eu-cookie-confirmation"],
     "reject": ["#hs-eu-decline-button"],
     "accept": ["#hs-eu-confirmation-button"]},
)

# Generic heuristic — text patterns for a reject/accept control when no named
# adapter matched. Used only to attempt operation; a match is still labelled
# "generic heuristic" in the ledger, not a specific vendor.
_REJECT_TEXT = re.compile(r"\b(reject all|reject|decline all|decline|refuse|only necessary|"
                          r"necessary only|deny|do not accept)\b", re.I)
_ACCEPT_TEXT = re.compile(r"\b(accept all|accept|allow all|agree|got it|i agree)\b", re.I)

# Substrings that identify a CMP was PRESENT even if no adapter matched — so we
# can say "a banner was present but not operable" rather than "no banner".
_CMP_PRESENCE_MARKERS = ("cookie", "consent", "gdpr", "ccpa", "privacy choices",
                         "onetrust", "cookiebot", "cookieyes", "termly", "usercentrics",
                         "quantcast", "trustarc", "osano", "iubenda")


def detect_cmp_in_html(html):
    """Best-effort vendor detection from rendered HTML (for tests + a fast path).
    Returns vendor name, 'generic' if a banner is present but unrecognised, or
    None if no consent banner is apparent."""
    low = (html or "").lower()
    for a in CMP_ADAPTERS:
        # a cheap signal: the adapter's id/class tokens appear in the DOM
        for sel in a["detect"]:
            token = sel.lstrip("#.").split(":")[0].split("[")[0]
            if token and token.lower() in low:
                return a["vendor"]
    if any(m in low for m in _CMP_PRESENCE_MARKERS) and (
            _REJECT_TEXT.search(low) or "cookie" in low):
        return "generic"
    return None


def adapter_for(vendor):
    for a in CMP_ADAPTERS:
        if a["vendor"] == vendor:
            return a
    return None


def is_reject_text(text):
    return bool(_REJECT_TEXT.search(text or ""))


def is_accept_text(text):
    return bool(_ACCEPT_TEXT.search(text or ""))
