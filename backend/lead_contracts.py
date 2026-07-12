"""Verified Lead Delivery — contracts by observation + drift validation.

Pure logic: given what the passive audit + a hydrated render observed about a
form, draft a contract (what "intact" means); and given a confirmed contract +
a fresh observation, find drift. No I/O, so every rule is unit-testable and the
numbers/consequences trace to observed reality.

Honest scope: this describes ONE designated pipeline per form (the fields and
destination we can observe), not every downstream automation. Nothing here
submits anything — that is Wave 2, behind its own rails.
"""
import hashlib
import re

# Injected on the observation render so JS that reads URL params populates the
# hidden tracking inputs — that's how we learn a field is JS-populated.
OBSERVE_PARAMS = "utm_source=lspy-test&utm_medium=lspy-test&gclid=lspy-test&fbclid=lspy-test"

# Fields whose loss silently breaks ad attribution — high severity, and the
# consequence is specific and expensive.
_ATTRIBUTION_RE = re.compile(
    r"^(gclid|gbraid|wbraid|fbclid|msclkid|ttclid|li_fat_id|dclid|"
    r"utm_[a-z]+|hutk|_ga|_gid|mc_eid)$", re.I)

_HIDDEN_TYPES = {"hidden"}


def _get(o, k, default=None):
    return o.get(k, default) if isinstance(o, dict) else getattr(o, k, default)


def contract_key(site_id, page_url, form_id="", selector="") -> str:
    """Stable id for a form across contract versions."""
    raw = f"{site_id}|{page_url}|{form_id}|{selector}".encode("utf-8", "ignore")
    return hashlib.sha1(raw).hexdigest()


def is_attribution_field(name) -> bool:
    return bool(name and _ATTRIBUTION_RE.match(name.strip()))


# ─── Destination detection ───────────────────────────────────────────────────
_HS_PORTAL_RE = re.compile(r"(?:portalId|portal-id)['\"]?\s*[:=]\s*['\"]?(\d{4,})", re.I)
_HS_FORM_RE = re.compile(r"(?:formId|form-id|data-form-id)['\"]?\s*[:=]\s*['\"]?([0-9a-f-]{20,})", re.I)


def detect_destination(action_url="", embed_scripts=(), embed_attrs="", scripts_text=""):
    """Best-effort {type, ids}. 'unknown' when we genuinely can't tell — never guessed."""
    blob = " ".join([embed_attrs or "", scripts_text or "", " ".join(embed_scripts or [])])
    low = blob.lower()
    action = (action_url or "").lower()

    if "hsforms.net" in low or "hsforms.com" in low or "hubspot" in low or "hs-form" in low or "hbspt" in low:
        ids = {}
        m = _HS_PORTAL_RE.search(blob)
        if m:
            ids["portal_id"] = m.group(1)
        m = _HS_FORM_RE.search(blob)
        if m:
            ids["form_id"] = m.group(1)
        return {"type": "hubspot", "ids": ids}
    if "leadconnectorhq" in low or "gohighlevel" in low or "msgsndr" in low or "highlevel" in low:
        m = re.search(r"/form/([0-9a-zA-Z]{6,})", blob)
        return {"type": "ghl", "ids": ({"form_id": m.group(1)} if m else {})}
    if action.startswith(("http://", "https://")):
        return {"type": "webhook", "ids": {"action_url": action_url}}
    return {"type": "unknown", "ids": {}}


# ─── Event detection (submit-intent conversions, statically identifiable) ────
_EVENT_PATTERNS = (
    (re.compile(r"gtag\(\s*['\"]event['\"]\s*,\s*['\"]([^'\"]+)['\"]", re.I), "gtag"),
    (re.compile(r"fbq\(\s*['\"]track['\"]\s*,\s*['\"]([^'\"]+)['\"]", re.I), "fbq"),
    (re.compile(r"dataLayer\.push\(\s*\{[^}]*['\"]event['\"]\s*:\s*['\"]([^'\"]+)['\"]", re.I), "dataLayer"),
)
_LEADISH = re.compile(r"lead|conversion|signup|sign_up|contact|submit|purchase|generate_lead", re.I)


def detect_events(scripts_text=""):
    """Conversion-ish events we can see in the page scripts. Deduped."""
    found = {}
    for rx, trigger in _EVENT_PATTERNS:
        for name in rx.findall(scripts_text or ""):
            if _LEADISH.search(name):
                found[(trigger, name)] = {"trigger": trigger, "name": name, "required_params": []}
    return list(found.values())


# ─── Draft a contract from observation ───────────────────────────────────────
def _field_kind(field):
    t = (_get(field, "type") or "").lower()
    return "hidden" if t in _HIDDEN_TYPES else "visible"


def draft_from_observation(observed_form, page_url, hydrated_values=None, scripts_text=""):
    """Turn one observed form into a DRAFT contract. `hydrated_values` maps a
    field name → its value after a hydrated render (with OBSERVE_PARAMS); used to
    learn which hidden inputs are JS-populated. Draft is never auto-confirmed."""
    hydrated_values = hydrated_values or {}
    fields = []
    for f in _get(observed_form, "fields") or []:
        name = (_get(f, "name") or "").strip()
        if not name:
            continue
        kind = _field_kind(f)
        if kind == "hidden":
            val = (hydrated_values.get(name) or "").strip()
            # A hidden input carrying a value after hydration is script/URL-populated.
            populated_by = "js" if val else "static"
            fields.append({
                "name": name, "required": bool(_get(f, "required")),
                "kind": "hidden", "populated_by": populated_by,
                "expected_crm_property": None,
            })
        else:
            fields.append({
                "name": name, "required": bool(_get(f, "required")),
                "kind": "visible", "populated_by": "user",
                "expected_crm_property": _guess_crm_property(name, _get(f, "type")),
            })

    form_id = _get(observed_form, "identifier") or ""
    destination = detect_destination(
        action_url=_get(observed_form, "action_url") or "",
        embed_scripts=_get(observed_form, "embed_scripts") or (),
        embed_attrs=str(_get(observed_form, "identifier") or ""),
        scripts_text=scripts_text,
    )
    return {
        "form_ref": {"page_url": page_url, "form_id": form_id,
                     "selector": _selector_for(observed_form)},
        "status": "draft",
        "fields": fields,
        "destination": destination,
        "events": detect_events(scripts_text),
    }


def _selector_for(form):
    fid = _get(form, "identifier")
    if fid:
        return f"#{fid}" if not str(fid).startswith("#") else str(fid)
    idx = _get(form, "index")
    return f"form:nth-of-type({(idx or 0) + 1})"


def _guess_crm_property(name, ftype):
    n = (name or "").lower()
    if ftype == "email" or "email" in n:
        return "email"
    if "phone" in n or "tel" in n or ftype == "tel":
        return "phone"
    if "first" in n and "name" in n:
        return "firstname"
    if "last" in n and "name" in n:
        return "lastname"
    if n in ("name", "fullname", "full_name", "your-name"):
        return "firstname"
    if "company" in n or "organization" in n:
        return "company"
    return None


# ─── Drift validation: confirmed contract vs a fresh observation ─────────────
def _consequence(kind, field_name, first_seen):
    seen = f" since {first_seen}" if first_seen else ""
    if is_attribution_field(field_name):
        return (f"`{field_name}` no longer reaches the destination → "
                f"ad-platform conversions are unattributable{seen}.")
    return {
        "field_removed": f"The `{field_name}` field is gone → those submissions arrive incomplete{seen}.",
        "not_populated": f"Hidden field `{field_name}` is no longer populated → its data is silently lost{seen}.",
        "required_drift": f"`{field_name}` changed its required state → validation/routing may differ{seen}.",
        "destination_changed": f"The form now submits somewhere else → leads may not reach the CRM at all{seen}.",
    }.get(kind, f"`{field_name}` drifted from the confirmed contract{seen}.")


def validate_drift(contract, observed_form, hydrated_values=None, first_seen=None):
    """Compare a CONFIRMED contract against a fresh observation → violations.
    Each: {kind, field, severity, consequence}. Severity: attribution=high,
    destination change=critical, visible-required removal=high, else medium."""
    hydrated_values = hydrated_values or {}
    observed_fields = {(_get(f, "name") or "").strip(): f
                       for f in (_get(observed_form, "fields") or []) if _get(f, "name")}
    violations = []

    for cf in _get(contract, "fields") or []:
        name = cf.get("name")
        if not name:
            continue
        of = observed_fields.get(name)
        if of is None:
            sev = "high" if (is_attribution_field(name) or (cf.get("kind") == "visible" and cf.get("required"))) else "medium"
            violations.append({"kind": "field_removed", "field": name, "severity": sev,
                               "consequence": _consequence("field_removed", name, first_seen)})
            continue
        # hidden field that used to be JS-populated but is now empty
        if cf.get("kind") == "hidden" and cf.get("populated_by") == "js":
            val = (hydrated_values.get(name) or "").strip()
            if not val:
                sev = "high" if is_attribution_field(name) else "medium"
                violations.append({"kind": "not_populated", "field": name, "severity": sev,
                                   "consequence": _consequence("not_populated", name, first_seen)})
        # required-flag drift
        if bool(cf.get("required")) != bool(_get(of, "required")):
            violations.append({"kind": "required_drift", "field": name, "severity": "medium",
                               "consequence": _consequence("required_drift", name, first_seen)})

    # destination change → critical
    obs_dest = detect_destination(
        action_url=_get(observed_form, "action_url") or "",
        embed_scripts=_get(observed_form, "embed_scripts") or (),
        embed_attrs=str(_get(observed_form, "identifier") or ""),
    )
    con_dest = _get(contract, "destination") or {}
    if con_dest.get("type") not in (None, "unknown") and obs_dest.get("type") not in (None, "unknown"):
        if (con_dest.get("type"), con_dest.get("ids")) != (obs_dest.get("type"), obs_dest.get("ids")):
            violations.append({"kind": "destination_changed", "field": "(destination)", "severity": "critical",
                               "consequence": _consequence("destination_changed", "(destination)", first_seen)})
    return violations


# ─── Observation render (the ONE impure function: loads the page hydrated) ───
_OBSERVE_JS = r"""
() => {
  const trackRe = /hsforms|hubspot|hbspt|msgsndr|leadconnector|highlevel|typeform|jotform/i;
  const embed = Array.from(document.querySelectorAll('script[src]'))
    .map(s => s.src).filter(s => trackRe.test(s));
  const forms = Array.from(document.querySelectorAll('form')).map((form, index) => ({
    index,
    identifier: form.id || form.getAttribute('name') || '',
    action_url: form.action || '',
    embed_scripts: embed,
    fields: Array.from(form.elements || [])
      .filter(el => ['input','select','textarea'].includes(el.tagName.toLowerCase()))
      .map(el => ({
        tag: el.tagName.toLowerCase(),
        type: (el.getAttribute('type') || '').toLowerCase(),
        name: el.getAttribute('name') || '',
        id: el.id || '',
        required: !!(el.required || el.getAttribute('aria-required') === 'true'),
        value: el.value || '',
      })),
  }));
  const scripts_text = Array.from(document.querySelectorAll('script:not([src])'))
    .map(s => s.textContent || '').join('\n').slice(0, 50000);
  return { forms, scripts_text };
}
"""


async def observe_page_forms(page_url: str) -> dict:
    """Render `page_url` with the observation params so JS populates tracking
    inputs, then read every form's fields + post-hydration values. Returns
    {forms:[...], scripts_text}. Best-effort; raises only on a hard launch error."""
    from playwright.async_api import async_playwright

    sep = "&" if "?" in page_url else "?"
    target = f"{page_url}{sep}{OBSERVE_PARAMS}"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            ctx = await browser.new_context()
            page = await ctx.new_page()
            await page.goto(target, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1200)   # let hydration/tracking scripts run
            data = await page.evaluate(_OBSERVE_JS)
        finally:
            await browser.close()
    return data


def hydrated_values_for(form) -> dict:
    """name -> value for a form's fields (from an observed render)."""
    out = {}
    for f in _get(form, "fields") or []:
        name = (_get(f, "name") or "").strip()
        if name:
            out[name] = _get(f, "value") or ""
    return out


def find_form(observed, form_id="", index=None):
    """Pick the observed form matching a contract's form_ref."""
    forms = observed.get("forms", []) if isinstance(observed, dict) else (observed or [])
    if form_id:
        for f in forms:
            if (_get(f, "identifier") or "") == form_id:
                return f
    if index is not None:
        for f in forms:
            if _get(f, "index") == index:
                return f
    return forms[0] if forms else None
