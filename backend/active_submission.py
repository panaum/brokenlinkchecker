"""
Active form testing — OPT-IN, feature-flagged, DEFAULT OFF.

DANGER: this is the ONE module in LinkSpy that creates real submissions. The
passive audit reads a form; this fills and sends it. A wrong move spams a
client's CRM and their sales team's phones. Every rail below is mandatory and
none of them is a suggestion:

  1. GLOBAL FLAG, DEFAULT OFF. Without ACTIVE_FORM_TESTING=on in the environment,
     the whole capability is inert — the endpoint refuses.
  2. PER-FORM OPT-IN. On top of the flag, a specific form must be explicitly
     enabled by a human before it can EVER be submitted. There is no "test all
     forms" switch, anywhere.
  3. PAYMENT FORMS ARE REFUSED. Card fields or a Stripe/PayPal iframe -> hard
     refusal, regardless of opt-in. We never risk a real charge.
  4. HONEYPOTS / HIDDEN / FILE FIELDS ARE NEVER FILLED. Filling a honeypot marks
     the submission as a bot and can taint the client's spam scoring.
  5. EXACTLY ONCE. One run submits one time. The executor presses submit once,
     with retries disabled.
  6. NEVER SCHEDULED. This is manual-trigger only. The monitoring scheduler has
     no code path to it — enforced by a test.

The decision logic here is PURE and exhaustively tested; the Playwright executor
(active_submission_exec.py) is a thin wrapper that only carries out a plan this
module produced. Tests never submit anything to the network.
"""
import os
import re
from urllib.parse import urlparse


# ─── the global flag ─────────────────────────────────────────────────────────
ACTIVE_FORM_TESTING_FLAG = "ACTIVE_FORM_TESTING"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def active_testing_enabled() -> bool:
    """The global kill-switch. Anything but an explicit truthy value is OFF."""
    return os.getenv(ACTIVE_FORM_TESTING_FLAG, "").strip().lower() in _TRUTHY


TEST_VALUE = "LINKSPY-TEST"


# ─── honeypots ───────────────────────────────────────────────────────────────
# Bot-trap fields. A real user never sees or fills these; a bot that fills every
# input does. Filling one tells the client's system "this was a bot", which is
# exactly the label we must not earn.
_HONEYPOT_NAMES = re.compile(
    r"(honey ?pot|_?gotcha|^hp$|^hp[_-]|[_-]hp$|winnie|\bbotcheck\b|"
    r"leaveblank|leave[-_]?this[-_]?blank|no[-_]?fill|fakefield|"
    r"^b_\d|url_?field|website_?url_?hp)",
    re.I,
)


def _get(field, key, default=None):
    if isinstance(field, dict):
        return field.get(key, default)
    return getattr(field, key, default)


def is_honeypot(field, form_visible: bool = True) -> bool:
    """Named like a trap, or — when the FORM is on screen — hidden/zero-size.

    A `type=hidden` input is handled separately (never fillable); a honeypot is
    the sneakier kind, a text input the CSS hides from humans.

    `form_visible` is critical: a closed modal form renders every field at
    `visible=false` and 0x0, which would misread every real field as a honeypot.
    Geometry only distinguishes a honeypot when its siblings are visible — i.e.
    when the form itself is shown. On a hidden form we fall back to names only.
    """
    for token in ((_get(field, "name") or "").strip(), (_get(field, "id") or "").strip()):
        if token and _HONEYPOT_NAMES.search(token):
            return True
    ftype = (_get(field, "type") or "").lower()
    if ftype in ("hidden", "submit", "button", "image", "reset"):
        return False   # not a honeypot per se; excluded elsewhere
    if not form_visible:
        return False   # geometry is unreliable on a closed form — names only
    if _get(field, "visible") is False:
        return True
    w, h = _get(field, "width"), _get(field, "height")
    if w is not None and h is not None and (w < 2 or h < 2):
        return True
    return False


# ─── payment detection (refuse) ──────────────────────────────────────────────
_PAYMENT_NAME_RE = re.compile(
    r"(card[-_ ]?number|cardnum|ccnum|cc[-_ ]?number|creditcard|credit[-_ ]?card|"
    r"\bcvc\b|\bcvv\b|\bcsc\b|security[-_ ]?code|card[-_ ]?code|"
    r"exp(iry|iration)?[-_ ]?(date|month|year)?|card[-_ ]?holder)",
    re.I,
)
_PAYMENT_AUTOCOMPLETE = re.compile(r"cc-(number|csc|exp|name)", re.I)
_PAYMENT_IFRAME_HOSTS = (
    "js.stripe.com", "checkout.stripe.com", "hooks.stripe.com", "m.stripe",
    "paypal.com", "paypalobjects.com", "braintreegateway.com", "braintree",
    "squareup.com", "square.com", "checkout.com", "adyen.com", "razorpay.com",
    "gocardless.com", "authorize.net", "2checkout.com",
)


def is_payment_field(field) -> bool:
    name = " ".join(str(_get(field, k) or "") for k in ("name", "id", "placeholder", "autocomplete"))
    if _PAYMENT_NAME_RE.search(name):
        return True
    if _PAYMENT_AUTOCOMPLETE.search(_get(field, "autocomplete") or ""):
        return True
    return False


def is_payment_form(fields, iframe_srcs=()) -> tuple:
    """(is_payment, reason). Any card field OR a known payment iframe host."""
    for src in iframe_srcs or ():
        low = (src or "").lower()
        if any(host in low for host in _PAYMENT_IFRAME_HOSTS):
            return True, f"a payment iframe is present ({urlparse(src).netloc or src})"
    for f in fields or []:
        if is_payment_field(f):
            label = _get(f, "name") or _get(f, "id") or "a card field"
            return True, f"a payment field is present ({label})"
    return False, ""


# ─── what is safe to fill ────────────────────────────────────────────────────
_FILLABLE_TYPES = frozenset({"text", "email", "tel", "url", "search", "number", "", "textarea"})
_SKIP_TYPES = frozenset({"hidden", "file", "submit", "button", "image", "reset", "password"})


def is_fillable(field, form_visible: bool = True) -> bool:
    """A visible, human-facing text field we may put test data into.

    Not a honeypot, not a payment field, not a file/hidden/submit control, and —
    importantly — never a password field (we do not invent credentials).
    """
    tag = (_get(field, "tag") or "").lower()
    if tag not in ("input", "textarea"):
        return False
    ftype = (_get(field, "type") or "").lower()
    if tag == "textarea":
        ftype = "textarea"
    if ftype in _SKIP_TYPES:
        return False
    if ftype not in _FILLABLE_TYPES:
        return False
    if is_honeypot(field, form_visible):
        return False
    if is_payment_field(field):
        return False
    # Only fill a field a human could actually use: on screen and laid out. A
    # 0x0 "visible" field means the form is not really open (apexure's contact
    # modal renders every field at 0x0 until triggered).
    if _get(field, "visible") is False:
        return False
    w, h = _get(field, "width"), _get(field, "height")
    if w is not None and h is not None and (w < 2 or h < 2):
        return False
    return True


def default_test_email(site_url: str) -> str:
    """qa+linkspy@{client-domain} — a filterable address the client can ignore
    in their CRM and automations."""
    host = (urlparse(site_url).netloc or site_url or "").lower().lstrip("www.")
    host = host.split(":")[0]
    domain = host[4:] if host.startswith("www.") else host
    return f"qa+linkspy@{domain}" if domain else "qa+linkspy@example.com"


def value_for(field, test_email: str) -> str:
    """The test value for a fillable field. Emails get the filterable address so
    the client can route it to trash; everything else gets LINKSPY-TEST."""
    ftype = (_get(field, "type") or "").lower()
    name = (_get(field, "name") or "") + (_get(field, "id") or "")
    if ftype == "email" or "email" in name.lower():
        return test_email
    if ftype == "tel" or "phone" in name.lower():
        return "5555550100"           # a documented non-routable test number
    if ftype == "number":
        return "1"
    if ftype == "url":
        return "https://linkspy-test.example"
    return TEST_VALUE


# ─── the submission plan (pure) ──────────────────────────────────────────────
def plan_submission(fields, iframe_srcs=(), test_email: str = "qa+linkspy@example.com",
                    form_visible: bool = True) -> dict:
    """Decide what a single test submission would do — WITHOUT doing it.

    Returns {refuse, fills, skipped, submitted_once}. `refuse` is a string reason
    when the form must not be touched; otherwise None. `fills` is the exact list
    the executor will type, `skipped` is everything deliberately left alone with
    why. This is the audited record of a submission before it happens.

    `form_visible=False` refuses: a hidden form (a modal that never opened) can't
    be filled correctly and its field geometry is unreadable, so we do not guess.
    """
    is_pay, reason = is_payment_form(fields, iframe_srcs)
    if is_pay:
        return {"refuse": f"This is a payment form — {reason}. LinkSpy never "
                          f"submits payment forms.",
                "fills": [], "skipped": [], "submitted_once": False}

    if not form_visible:
        return {"refuse": "The target form is not visible on the page — it may be "
                          "a modal that opens on click. Open it (or point the "
                          "selector at the opened form) before testing; we do not "
                          "fill a form we cannot see.",
                "fills": [], "skipped": [], "submitted_once": False}

    fills, skipped = [], []
    for f in fields or []:
        name = _get(f, "name") or _get(f, "id") or ""
        ftype = (_get(f, "type") or "").lower()
        if is_fillable(f, form_visible):
            fills.append({"name": name, "type": ftype,
                          "value": value_for(f, test_email)})
        else:
            skipped.append({"name": name, "type": ftype,
                            "reason": _skip_reason(f, form_visible)})

    # Never submit a blank form. If nothing was safely fillable — every field a
    # honeypot, hidden, zero-size, or a control — the form is not in a fillable
    # state (an un-opened modal, a wizard step). Clicking submit on it would post
    # an empty payload or fail validation; refuse instead.
    if not fills:
        return {"refuse": "No visible, fillable field was found on this form, so "
                          "there is nothing to submit. If it opens on click "
                          "(a modal or multi-step form), open it first.",
                "fills": [], "skipped": skipped, "submitted_once": False}

    return {"refuse": None, "fills": fills, "skipped": skipped,
            "submitted_once": True}


def _skip_reason(field, form_visible: bool = True) -> str:
    ftype = (_get(field, "type") or "").lower()
    if is_honeypot(field, form_visible):
        return "honeypot / hidden trap — filling it would flag us as a bot"
    if is_payment_field(field):
        return "payment field — never filled"
    if ftype == "file":
        return "file input — never uploaded"
    if ftype == "hidden":
        return "hidden field — left as the site set it"
    if ftype == "password":
        return "password — we do not invent credentials"
    return f"{ftype or 'control'} — not a fillable text field"
