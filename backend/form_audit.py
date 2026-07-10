"""
Passive form audit.

A broken form is invisible. The page looks perfect, the visitor types their
details, presses send — and the lead evaporates. Nothing 500s, nothing logs.
For a lead-gen client this is the single most expensive defect on the site.

THIS MODULE NEVER SUBMITS A FORM. It reads the DOM and checks the action URL
with an ordinary GET, through the checker every other link goes through. There
is no .submit(), no POST, no synthetic event, and no code path that fills a
field. Submitting would spam the client's CRM and their sales team's phones,
which is worse than the bug we are looking for.

Verdicts land in the existing buckets. The governing rule is stricter here than
for links: **when we cannot PROVE a form is broken, it is `unverifiable`.**
Telling a client their contact form is dead when it works costs more trust than
staying quiet.
"""
import re
from urllib.parse import urljoin, urlparse

from models import LinkResult, RawLink

FORM_ZONE = "Form"
FORM_KIND = "form"
FORM_ACTION_RESOURCE = "form_action"

# Hosts whose script renders the form. If it 404s, the form never appears at all.
_EMBED_HOSTS = (
    "hs-scripts.com", "hsforms.net", "embed.typeform.com", "form.jotform",
    "paperform", "formstack", "wufoo", "gravityforms", "marketo",
    "munchkin.js", "pardot", "leadconnectorhq", "msgsndr",
)

# Search boxes are forms, but a search box is not a lead-capture form and its
# "no submit button" state is normal (you press Enter). hubspot.com carries two
# of them — <input type=search name=q> with action="" and a JS listener — and
# an earlier version of this file was one CSS rule away from calling both dead.
_SEARCH_FIELD_NAMES = frozenset({"q", "s", "search", "query", "keyword", "term", "kw"})
_SEARCH_HINTS = ("search", "srch", "query")
# Anchored on word boundaries. Plain `"search" in haystack` matches "research".
_SEARCH_WORD_RE = re.compile(r"(?<![a-z])(search|srch|query)(?![a-z])")

# Fields a visitor actually fills in. A <form> containing only hidden inputs or
# a single button collects nothing, so there is nothing to report about it.
_NON_INPUT_TYPES = frozenset({"hidden", "submit", "button", "image", "reset"})


def _get(obj, field, default=None):
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


# ─────────────────────────────────────────────────────────────────────────────
# What a GET to a form's action actually tells you.
#
# Almost nothing, most of the time. Verified against real endpoints:
#   EmailOctopus  -> 405
#   HubSpot forms -> 405
#   Formspree     -> 405
# They accept POST and nothing else. A 405/403 is the SIGN OF A HEALTHY FORM
# endpoint, not a broken one. Treating "not 200" as a problem would flag almost
# every form on the internet.
#
# And the checker maps 5xx to bucket "broken", so a POST-only endpoint that 500s
# on a GET would be reported as "submissions may be lost" — claiming a working
# form is dead. Only a status that proves the destination is GONE may do that.
# ─────────────────────────────────────────────────────────────────────────────
# 410 Gone is the server stating it, in the one status that has no other reading.
_EXPLICITLY_GONE = frozenset({410})

# A 404 is NOT proof. Next.js, Django and Rails all answer 404 to a GET on a
# route that only accepts POST. fautons.com/api/auth/request does exactly that —
# it serves the site's HTML 404 page — while OPTIONS returns 405 and POST signs
# you in. Calling that form dead told the client their working sign-in was
# broken. A 404 now needs corroboration before it may accuse.
_AMBIGUOUS_ON_GET = frozenset({404})

# The endpoint answered, and refused a GET. That is exactly what it should do.
_EXPECTED_FOR_A_POST_ENDPOINT = frozenset({400, 401, 403, 405, 429})

# What an OPTIONS answer says about whether the route is there at all. A route
# that does not exist cannot answer "method not allowed".
_ROUTE_IS_THERE = frozenset({200, 201, 204, 400, 401, 403, 405, 501})

ACTION_GONE = "gone"
ACTION_FINE = "fine"
ACTION_UNCERTAIN = "uncertain"


def action_verdict(checked, options_status=None) -> str:
    """What the checked action result means for the FORM, not for a link.

    `options_status` is the reply to an OPTIONS probe of the same URL, when one
    was made. OPTIONS is idempotent and carries no body: it is not a submission.
    """
    if checked is None:
        return ACTION_UNCERTAIN

    status = _get(checked, "status_code")
    bucket = _get(checked, "bucket")

    if status in _EXPLICITLY_GONE:
        return ACTION_GONE
    # No status at all with a broken bucket means DNS failure or a refused
    # connection: the host the form posts to does not exist.
    if status is None and bucket == "broken":
        return ACTION_GONE

    if status in _AMBIGUOUS_ON_GET:
        if options_status in _ROUTE_IS_THERE:
            return ACTION_FINE          # the route exists; it just will not GET
        if options_status in _EXPLICITLY_GONE or options_status == 404:
            return ACTION_GONE          # two methods, same answer: it is not there
        return ACTION_UNCERTAIN         # could not corroborate — do not accuse

    if status in _EXPECTED_FOR_A_POST_ENDPOINT:
        return ACTION_FINE
    if bucket == "ok":
        return ACTION_FINE
    return ACTION_UNCERTAIN


OPTIONS_TIMEOUT_SECONDS = 8.0


async def probe_action_methods(results, client=None) -> dict:
    """Ask a 404-ing form action whether its route exists, with OPTIONS.

    OPTIONS is idempotent, carries no body, and by RFC 9110 must have no side
    effects. It is a question, not a submission — the browser itself sends one
    before every cross-origin POST. WE NEVER POST.

    Returns {action_url: options_status_or_None}. Only URLs that answered a GET
    with 404 are probed: everywhere else the GET already told us enough.

    Kept out of classify_form and audit_forms on purpose, so those stay pure and
    provably issue no request at all.
    """
    import httpx
    from checker import _browser_headers

    targets = sorted({
        _get(r, "url") for r in (results or [])
        if _get(r, "resource_type") == FORM_ACTION_RESOURCE
        and _get(r, "status_code") in _AMBIGUOUS_ON_GET
    })
    if not targets:
        return {}

    owned = client is None
    if owned:
        client = httpx.AsyncClient(follow_redirects=True,
                                   timeout=OPTIONS_TIMEOUT_SECONDS)
    statuses = {}
    try:
        for url in targets:
            try:
                response = await client.request(
                    "OPTIONS", url, headers=_browser_headers(url))
                statuses[url] = response.status_code
            except Exception:
                statuses[url] = None      # unreachable: cannot corroborate
    finally:
        if owned:
            await client.aclose()
    return statuses


# ─────────────────────────────────────────────────────────────────────────────
# Static extraction — the DOM facts that do not need a browser.
# Visibility and overlay detection need computed styles, so they come from the
# Playwright pass (scraper._COLLECT_FORMS_JS) and are `None` here: unknown.
# ─────────────────────────────────────────────────────────────────────────────
_SUBMIT_SELECTORS = (
    "button[type=submit]",
    "input[type=submit]",
    "input[type=image]",
)


def _has_submit_control(form) -> bool:
    for selector in _SUBMIT_SELECTORS:
        if form.select_one(selector):
            return True
    # HTML spec: a <button> with no type inside a form is an implicit submit.
    for button in form.find_all("button"):
        if not button.get("type"):
            return True
    return False


def _statically_hidden(form) -> bool:
    if form.has_attr("hidden"):
        return True
    style = (form.get("style") or "").lower().replace(" ", "")
    return "display:none" in style or "visibility:hidden" in style


def _label_of(form, index: int) -> str:
    for source in (form.get("aria-label"), form.get("id"), form.get("name")):
        if source and source.strip():
            return source.strip()[:60]
    heading = form.find(["legend", "h1", "h2", "h3", "h4"])
    if heading and heading.get_text(strip=True):
        return heading.get_text(strip=True)[:60]
    return f"Form #{index + 1}"


def extract_forms(soup, page_url: str) -> list:
    """Every <form>, as the JS pass would report it minus runtime visibility.

    Used by the tests and as a fallback when the browser evaluate fails. Reads
    the DOM only.
    """
    forms = []
    for index, form in enumerate(soup.find_all("form")):
        action_raw = form.get("action")
        fields = [
            {
                "tag": el.name,
                "type": (el.get("type") or "").lower(),
                "name": el.get("name") or "",
                "id": el.get("id") or "",
                "placeholder": el.get("placeholder") or "",
                "required": el.has_attr("required") or el.get("aria-required") == "true",
            }
            for el in form.find_all(["input", "select", "textarea"])
        ]
        required = [f for f in fields if f["required"]]
        embed_scripts = [
            s["src"] for s in soup.find_all("script", src=True)
            if any(host in s["src"].lower() for host in _EMBED_HOSTS)
        ]
        forms.append({
            "index": index,
            "identifier": form.get("id") or form.get("name") or "",
            "label": _label_of(form, index),
            "role": form.get("role") or "",
            "action_raw": action_raw,
            "method": (form.get("method") or "get").lower(),
            "action_url": urljoin(page_url, action_raw) if action_raw else "",
            "has_submit": _has_submit_control(form),
            "has_inline_onsubmit": bool(form.get("onsubmit")),
            "has_js_submit_listener": bool(form.get("data-js-listener")),
            "field_count": len(form.find_all(["input", "select", "textarea", "button"])),
            "fields": fields,
            "required_fields": required,
            "visible": False if _statically_hidden(form) else None,
            "hidden_reason": "css" if _statically_hidden(form) else "",
            "covered": None,
            "embed_scripts": embed_scripts,
            "has_embed_container": bool(
                soup.select_one(".hs-form, .hs-form-frame, [data-hs-forms], "
                                "[data-form-id], .typeform-widget, .jotform-form")
            ),
        })
    return forms


# ─────────────────────────────────────────────────────────────────────────────
# Reuse the existing checker: a form action is just a URL.
# ─────────────────────────────────────────────────────────────────────────────
def form_action_links(forms, page_url: str, already_seen=()) -> list:
    """RawLinks for each distinct form action, so check_all_links checks them.

    Only http(s) actions. `mailto:` actions and JS-only forms have nothing to
    fetch.
    """
    seen = set(already_seen)
    links = []
    for form in forms or []:
        action = _get(form, "action_url") or ""
        if not action.lower().startswith(("http://", "https://")):
            continue
        if action in seen:
            continue
        seen.add(action)
        links.append(RawLink(
            url=action,
            source_element="form",
            anchor_text=_get(form, "label") or "Form",
            category=FORM_ZONE,
            is_external=urlparse(action).netloc != urlparse(page_url).netloc,
            zones=[FORM_ZONE],
            link_kind="http",
            resource_type=FORM_ACTION_RESOURCE,
            priority="critical",   # a form is a conversion path
        ))
    return links


def _embed_is_down(form, results_by_url: dict, signals: dict) -> str:
    """The URL of a form-embed script that failed to load, or ""."""
    failed = {
        entry["url"] for entry in (signals or {}).get("http_errors", [])
        if entry.get("status", 0) >= 400
    }
    failed |= {entry["url"] for entry in (signals or {}).get("failed_requests", [])}

    for src in _get(form, "embed_scripts") or []:
        if src in failed:
            return src
        checked = results_by_url.get(src)
        if checked is not None and _get(checked, "bucket") == "broken":
            return src
    return ""


def _is_search_form(form) -> bool:
    """A search box submits on Enter and needs no button. Judged on its FIELDS,
    not on its id — hubspot.com's search forms have no id, no label and no
    action, and only their <input type=search name=q> gives them away."""
    if (_get(form, "role") or "").lower() == "search":
        return True

    for field in _get(form, "fields") or []:
        if field.get("type") == "search":
            return True
        if field.get("name", "").lower() in _SEARCH_FIELD_NAMES:
            return True
        if any(h in field.get("placeholder", "").lower() for h in _SEARCH_HINTS):
            return True

    haystack = " ".join([
        str(_get(form, "identifier") or ""),
        str(_get(form, "label") or ""),
        str(_get(form, "action_url") or ""),
    ]).lower()
    # Word boundaries, not substrings: "/research/" contains "search", and a
    # "Download our research report" form must not be exempted as a search box.
    return bool(_SEARCH_WORD_RE.search(haystack))


def _input_fields(form) -> list:
    """Fields a visitor types into. Hidden inputs and buttons do not count."""
    return [
        f for f in (_get(form, "fields") or [])
        if f.get("type") not in _NON_INPUT_TYPES
        and f.get("tag") in ("input", "select", "textarea")
    ]


def _has_any_submit_handler(form, delegated: bool) -> bool:
    return bool(
        _get(form, "has_inline_onsubmit")
        or _get(form, "has_js_submit_listener")
        or delegated
    )


def _submits_natively(form, delegated: bool) -> bool:
    """True when the BROWSER does the submitting, so the HTML rules bind.

    A field with no `name` is only discarded when the browser serialises the
    form itself. React reads its values out of component state and posts them
    with fetch: `<input required>` with no name is completely normal there and
    works. A synthetic container has no <form> tag, so nothing is ever
    serialised natively.
    """
    if _get(form, "synthetic"):
        return False
    return not _has_any_submit_handler(form, delegated)


def classify_form(form, results_by_url: dict, signals: dict = None,
                  page_url: str = "") -> dict:
    """One verdict per form: {bucket, reason, confidence} or None if healthy.

    Ordered by what we can PROVE, not by what looks alarming. Anything unproven
    is `unverifiable` — over-claiming on a form costs more than staying quiet.
    """
    signals = signals or {}
    delegated = bool(signals.get("delegated"))
    action_url = _get(form, "action_url") or ""
    action_raw = _get(form, "action_raw")
    checked = results_by_url.get(action_url) if action_url else None
    options_status = (signals.get("action_options") or {}).get(action_url)
    label = _get(form, "label") or "This form"

    # 1. The destination is provably gone: 410, a host that does not resolve, or
    #    a 404 that an OPTIONS probe agrees with. Anything short of proof — a
    #    405, a 403, a 500, a lone 404 — is not enough: see action_verdict.
    verdict = action_verdict(checked, options_status)
    if verdict == ACTION_GONE:
        status = _get(checked, "status_code")
        detail = f"returns {status}" if status else "no longer exists"
        return {
            "bucket": "dead_cta",
            "confidence": "high",
            "reason": (f"{label} posts to a page that {detail} — "
                       f"submissions may be lost"),
        }

    # 2. The script that renders the form is down, so the form never appears.
    embed = _embed_is_down(form, results_by_url, signals)
    if embed:
        return {
            "bucket": "dead_cta",
            "confidence": "high",
            "reason": (f"{label} is loaded by a script that is failing "
                       f"({embed.rsplit('/', 1)[-1]}) — the form never appears "
                       f"for visitors"),
        }

    # 3. A search box is not a lead-capture form. It submits on Enter, it has no
    #    button, and it is often action-less with a JS handler. Nothing below
    #    applies to it, and reporting it would add noise to nearly every site.
    if _is_search_form(form):
        return None

    # 4. A form the visitor cannot type anything into collects nothing. Usually
    #    a wrapper, a logout stub, or a single-button POST.
    if not _input_fields(form):
        return None

    # Visibility rules below apply to a real <form> element, whose box is the
    # form. A synthetic container is whichever ancestor <div> happened to hold
    # the inputs and the button: its box may be 0x0 while the fields inside
    # render perfectly (absolutely positioned children, contents display, …).
    # wix.com produced exactly that — "renders with no size" about its hero.
    synthetic = bool(_get(form, "synthetic"))

    # 5. Covered by something painted on top — a cookie wall, a stuck modal.
    #    This is the case worth reporting: the form is there and unreachable.
    if not synthetic and _get(form, "covered") is True:
        return {
            "bucket": "unverifiable",
            "confidence": "low",
            "reason": (f"{label} is covered by something else on the page — "
                       f"visitors may be unable to click it. Please check manually"),
        }

    # 6. Rendered, but with no size. That is a rendering failure, not a design.
    #    NOTE: plain display:none is NOT reported. It is the resting state of
    #    every modal contact form on the internet, and flagging it would mean
    #    telling most clients their working popup form "may be unreachable".
    if not synthetic and _get(form, "hidden_reason") == "zero-size":
        return {
            "bucket": "unverifiable",
            "confidence": "low",
            "reason": (f"{label} renders with no size — visitors may not be able "
                       f"to see or use it. Please check manually"),
        }
    if not synthetic and _get(form, "visible") is False:
        return None   # hidden by CSS: almost certainly a popup awaiting its trigger

    # 7. Nothing to press.
    if not _get(form, "has_submit"):
        return {
            "bucket": "dead_cta",
            "confidence": "high",
            "reason": f"{label} has no button to submit it — visitors cannot send it",
        }

    # 5. A required field with no name is never sent to the server. The visitor
    #    fills it in, and the value silently never arrives.
    #
    #    ONLY when the browser does the submitting. React reads its values from
    #    component state and posts them with fetch, so `<input required>` with no
    #    name is normal there and works fine. Firing this rule on a JS-driven
    #    form would call most modern contact forms broken.
    nameless = [f for f in (_get(form, "required_fields") or []) if not f.get("name")]
    if nameless and _submits_natively(form, delegated):
        which = nameless[0].get("id") or nameless[0].get("type") or "a field"
        return {
            "bucket": "broken",
            "confidence": "high",
            "reason": (f"{label} has a required field ({which}) that is never "
                       f"sent — what the visitor types there is discarded"),
        }

    # 6. No action and no handler anywhere: nothing happens on submit.
    if not action_raw and not _has_any_submit_handler(form, delegated):
        if _get(form, "synthetic"):
            # No <form> tag, so there is no native submit to fall back on, and we
            # found no click handler. That is suspicious but not proof: the
            # handler may be bound in a way the probe cannot see.
            return {
                "bucket": "unverifiable",
                "confidence": "low",
                "reason": (f"{label} collects details but we found no code that "
                           f"sends them. Please check manually"),
            }
        return {
            "bucket": "dead_cta",
            "confidence": "high",
            "reason": f"{label} submits nowhere — it has no destination and no handler",
        }
    if not action_raw:
        # A handler exists, or the page delegates its events. It probably works,
        # and we cannot prove otherwise without submitting it. We will not.
        return None

    # 7. The endpoint answered oddly — a timeout, or a 5xx. A POST-only endpoint
    #    can legitimately 500 on a GET, so this is a soft warning, never a break.
    #    A 405/403 says nothing at all and is not reported: it is what a healthy
    #    form endpoint does when you GET it.
    if verdict == ACTION_UNCERTAIN and checked is not None:
        return {
            "bucket": "unverifiable",
            "confidence": "low",
            "reason": (f"{label} posts to an address we could not check "
                       f"automatically. Please check manually"),
        }

    return None   # healthy


def _finding_url(form, page_url: str) -> str:
    """Stable identity across scans, so the diff can track a form."""
    action = _get(form, "action_url") or ""
    if action:
        return action
    # A synthetic container and a real <form> can both fall back to their index.
    # Namespace them, or form #1 and container #1 collide into one finding.
    prefix = "formless-" if _get(form, "synthetic") else "form-"
    identifier = _get(form, "identifier") or f"{prefix}{_get(form, 'index', 0) + 1}"
    return f"{page_url}#{identifier}"


# A 405 is the only status that PROVES the endpoint is alive: the server routed
# the request, recognised the resource, and refused the method. Every real form
# endpoint we tested answers a GET this way. The generic checker cannot know
# that and files it under "blocked", so the table renders a healthy Subscribe
# form as "Can't Verify". Here we know it is a form action, so we can say so.
#
# 401/403/429 stay unverifiable on purpose: those are equally the fingerprint of
# a bot wall in front of a page that may or may not exist.
_PROVES_ENDPOINT_LIVE = frozenset({405})


def relabel_form_actions(results, options_statuses: dict = None) -> int:
    """Promote form-action rows the checker mislabelled.

    The checker sees a URL, not a form. It calls a 405 `blocked` and a 404
    `broken` with the reason "an asset fails to load" — nonsense for a login
    endpoint. Here we know it is a form action, and we have an OPTIONS answer.

    Mutates in place. Returns how many rows were promoted.
    """
    options_statuses = options_statuses or {}
    promoted = 0
    for r in results or []:
        if _get(r, "resource_type") != FORM_ACTION_RESOURCE:
            continue
        if _get(r, "bucket") == "ok":
            continue

        status = _get(r, "status_code")
        options_status = options_statuses.get(_get(r, "url"))

        if status in _PROVES_ENDPOINT_LIVE:
            reason = (
                "Endpoint is live. It refuses GET with 405, which is exactly what "
                "a POST-only form endpoint does. We never POST, so we do not test "
                "the submission itself."
            )
        elif status in _AMBIGUOUS_ON_GET and options_status in _ROUTE_IS_THERE:
            reason = (
                f"Endpoint is live. A GET returns 404, but OPTIONS answers "
                f"{options_status} — the route exists and accepts POST. Many "
                f"frameworks serve their 404 page for the wrong method."
            )
        else:
            continue

        r.bucket = "ok"
        r.label = "ok"
        # Priority triages flagged items; this one is no longer flagged.
        r.priority = None
        r.error = None
        r.reason = reason
        promoted += 1
    return promoted


def _is_lead_form(form) -> bool:
    """A form a visitor gives you something through. Search boxes do not count."""
    return bool(_input_fields(form)) and not _is_search_form(form)


def _healthy_reason(form, delegated: bool) -> str:
    """Say what we proved, and name what we could not prove. No overclaiming."""
    parts = []
    revealed_by = _get(form, "revealed_by")
    if revealed_by:
        parts.append(f'Opened by the "{revealed_by}" button.')
    if _get(form, "synthetic"):
        parts.append("Built without a <form> tag, as most modern forms are.")
    if _get(form, "hidden_reason") == "css":
        parts.append("Hidden until opened, as a modal form is.")
    parts.append("The form renders, and it has a working submit path.")
    if _has_any_submit_handler(form, delegated) and not _get(form, "action_url"):
        parts.append(
            "It submits through JavaScript, so where it posts cannot be verified "
            "without submitting it — and we never submit."
        )
    return " ".join(parts)


def _healthy_form_row(form, page_url: str, delegated: bool) -> LinkResult:
    return LinkResult(
        url=_finding_url(form, page_url),
        source_element="form",
        anchor_text=_get(form, "label") or "Form",
        category=FORM_ZONE,
        is_external=False,
        zones=[FORM_ZONE],
        link_kind=FORM_KIND,
        resource_type=FORM_ACTION_RESOURCE,
        priority=None,           # nothing to triage
        bucket="ok",
        confidence="high",
        reason=_healthy_reason(form, delegated),
        label="ok",
        status_code=None,
        response_ms=0,
    )


def audit_forms(forms, results, signals: dict = None, page_url: str = "") -> list:
    """One LinkResult per form: the defect if there is one, else a healthy row.

    Reuses the checked results for the form actions rather than re-fetching.
    A healthy form used to yield nothing at all, which made "we looked and it is
    fine" indistinguishable from "we never looked".
    """
    results_by_url = {_get(r, "url"): r for r in (results or [])}
    delegated = bool((signals or {}).get("delegated"))
    relabel_form_actions(results, (signals or {}).get("action_options"))
    findings = []

    for form in forms or []:
        verdict = classify_form(form, results_by_url, signals, page_url)

        if not verdict:
            # Healthy. Show it only if it is a real lead form whose action is not
            # already a row of its own — otherwise the form appears twice.
            action = _get(form, "action_url") or ""
            if _is_lead_form(form) and not action.lower().startswith(("http://", "https://")):
                findings.append(_healthy_form_row(form, page_url, delegated))
            continue

        label = _get(form, "label") or "Form"
        findings.append(LinkResult(
            url=_finding_url(form, page_url),
            source_element="form",
            anchor_text=label,
            category=FORM_ZONE,
            is_external=False,
            zones=[FORM_ZONE],
            link_kind=FORM_KIND,
            resource_type=FORM_ACTION_RESOURCE,
            priority="critical",
            bucket=verdict["bucket"],
            confidence=verdict["confidence"],
            reason=verdict["reason"],
            label=_LABELS[verdict["bucket"]],
            status_code=None,
            response_ms=0,
            error=verdict["reason"],
        ))

    return findings


# The bucket is authoritative; `label` keeps the older UI paths working.
_LABELS = {
    "dead_cta": "dead_cta",
    "broken": "broken",
    "unverifiable": "blocked",
}
