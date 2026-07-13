"""Consent verdict engine — deterministic, per regime, per page.

THE WORDING LAW (absolute): this engine OBSERVES AND RECORDS technical behavior.
It NEVER certifies compliance, never says "compliant/non-compliant", never gives
legal advice. Every output is an *observation* phrased as a fact about what fired
and when, plus a DESCRIPTIVE (not advisory) note about the relevant regime.

Where the CMP could not be operated or the render was blocked, the engine emits
a DECLARED LIMITATION — never a verdict.
"""
from consent_classify import consent_class, ADTECH, ANALYTICS_C, FUNCTIONAL, ESSENTIAL, UNKNOWN

ENGINE_VERSION = 1

# The fixed scope statement — present on every session, surface, and document.
SCOPE_STATEMENT = ("Technical observation of tracking behavior. Not legal advice; "
                   "consult counsel for compliance determinations.")

# Severity of a non-essential firing, by class.
_SEV_BY_CLASS = {ADTECH: "critical", ANALYTICS_C: "high", FUNCTIONAL: "medium"}


def _obs(regime, code, severity, statement, citation, evidence=None):
    return {"kind": "observation", "regime": regime, "code": code, "severity": severity,
            "statement": statement, "citation": citation, "evidence": evidence or {}}


def _limitation(regime, code, statement):
    return {"kind": "limitation", "regime": regime, "code": code, "severity": "info",
            "statement": statement, "citation": "", "evidence": {}}


def _class_of(req):
    return req.get("consent_class") or consent_class(req.get("host", ""), req.get("url", "")).get("class")


def _non_essential(reqs):
    return [r for r in (reqs or []) if _class_of(r) in (ADTECH, ANALYTICS_C, FUNCTIONAL)]


def _label(req):
    prov = req.get("provenance") or ""
    return prov.split(".")[0] if prov else (req.get("host") or "a third-party request")


# ─── UK regime (UK GDPR + PECR — opt-in) ─────────────────────────────────────
def uk_verdicts(cold_requests, reject_requests, cmp):
    """cold_requests: fired on load with no interaction. reject_requests: fired
    after operating the reject control. cmp: {detected, operated, vendor,
    accept_clicks, reject_clicks, reject_depth}."""
    out = []
    cmp = cmp or {}

    # 1. Non-essential fired before any consent was given.
    for r in _non_essential(cold_requests):
        cls = _class_of(r)
        out.append(_obs("UK", "pre_consent_fire", _SEV_BY_CLASS.get(cls, "medium"),
                        f"{_label(r)} fired before any consent was given.",
                        "UK PECR requires consent before non-essential trackers are set.",
                        {"host": r.get("host"), "url": r.get("url"), "class": cls,
                         "ms_after_load": r.get("ms_after_load")}))

    # 2. Reject path — only judged if the CMP was actually operated.
    if not cmp.get("detected"):
        out.append(_limitation("UK", "cmp_undetected",
                   "No consent banner could be identified on this page; the reject-path behaviour was not observed."))
    elif not cmp.get("operated"):
        out.append(_limitation("UK", "cmp_not_operable",
                   f"A consent banner ({cmp.get('vendor', 'unknown')}) was detected but its reject control could not be operated; the reject-path behaviour was not observed."))
    else:
        for r in _non_essential(reject_requests):
            cls = _class_of(r)
            out.append(_obs("UK", "post_reject_fire", "critical",
                            f"{_label(r)} fired after the reject control was operated — inconsistent with a consent-gated setup.",
                            "Under UK PECR, non-essential trackers should not fire once consent is declined.",
                            {"host": r.get("host"), "url": r.get("url"), "class": cls}))
        # 3. Reject materially harder than accept (mechanical, documented heuristic).
        acc = cmp.get("accept_clicks")
        rej = cmp.get("reject_clicks")
        if acc is not None and rej is not None and (rej - acc) >= 2:
            out.append(_obs("UK", "reject_harder", "high",
                            f"The reject control is materially harder to reach than accept (accept: {acc} click(s), reject: {rej} click(s)).",
                            "Regulators describe accept/reject as needing comparable prominence.",
                            {"accept_clicks": acc, "reject_clicks": rej}))
    return out


# ─── US regime (CCPA/CPRA + GPC — opt-out) ───────────────────────────────────
def us_verdicts(gpc_requests, optout, cmp=None):
    """gpc_requests: fired with Sec-GPC:1 + navigator.globalPrivacyControl=true,
    no interaction. optout: {found, resolves, mechanism_present}."""
    out = []
    optout = optout or {}

    # 1. Adtech ("sharing") fired despite GPC.
    adtech = [r for r in (gpc_requests or []) if _class_of(r) == ADTECH]
    for r in adtech:
        out.append(_obs("US", "gpc_not_honored", "critical",
                        f"{_label(r)} fired while the Global Privacy Control signal was present — the browser signal was not honored.",
                        "CPRA treats GPC as a valid consumer opt-out-of-sale/sharing signal.",
                        {"host": r.get("host"), "url": r.get("url")}))

    # 2. Opt-out mechanism.
    if not optout.get("found"):
        out.append(_obs("US", "optout_missing", "high",
                        "No 'Do Not Sell or Share'-class opt-out mechanism was located on the page.",
                        "CPRA requires a clear method for consumers to opt out of sale/sharing.",
                        {}))
    elif not optout.get("resolves"):
        out.append(_obs("US", "optout_dead", "high",
                        "A 'Do Not Sell or Share' link was located but did not resolve (also a broken link).",
                        "An opt-out method that does not function does not provide the required mechanism.",
                        {}))
    elif not optout.get("mechanism_present"):
        out.append(_obs("US", "optout_no_mechanism", "medium",
                        "The opt-out link resolves but no operable mechanism (form or consent panel) was detected on its destination.",
                        "Existence and destination observed; end-to-end operation is not performed in this version.",
                        {}))
    return out


def scope_statement():
    return SCOPE_STATEMENT
