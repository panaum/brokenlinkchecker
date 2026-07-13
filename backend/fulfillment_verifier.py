"""Fulfillment verifier — does the promise's destination honor it?

Pure: takes a classified promise + an `evidence` dict assembled by joining
EXISTING data (the link's own bucket, destination forms/integrations/content-
type/redirects) and returns honored | broken | unverified with a one-line,
plain-language evidence string. Every rule cites the join it relies on.

Honesty rule, absolute: a destination that is bot-blocked / JS-gated / otherwise
unverifiable is "unverified" (neutral), NEVER broken.
"""

SCHEDULING, CRM_FORMS, CHAT, MEDIA, PAYMENT = (
    "Scheduling", "CRM/Forms", "Chat/Support", "Content/Media", "Payment")


def _r(verdict, evidence, severity=None):
    out = {"verdict": verdict, "evidence": evidence}
    if severity:
        out["severity"] = severity
    return out


def verify(promise, evidence):
    """promise: from promise_classifier.classify(); evidence: joined signals."""
    ev = evidence or {}
    ptype = promise.get("type")
    bucket = ev.get("link_bucket")
    ints = set(ev.get("integrations") or [])
    has_form = bool(ev.get("has_form"))

    # ── Destination status trumps everything ──
    if bucket == "unverifiable":
        return _r("unverified", "Destination couldn't be verified from here (bot-blocked or JS-gated).")
    if bucket in ("broken", "dead_cta"):
        return _r("broken", "The destination itself is broken — the promise leads nowhere.")

    # ── Tier 1 ──
    if ptype == "BOOK":
        if SCHEDULING in ints:
            return _r("honored", "Scheduling widget present (e.g. Calendly).")
        if has_form:
            return _r("honored", "A booking form is present on the destination.")
        return _r("broken", "Leads to a page with no way to book — no scheduler or form.")

    if ptype == "DOWNLOAD":
        if ev.get("is_file"):
            return _r("honored", "Destination is a downloadable file.")
        return _r("broken", "Promises a download but the destination is a page, not a file.")

    if ptype == "CONTACT":
        if has_form or CRM_FORMS in ints:
            return _r("honored", "A contact form is present.")
        return _r("broken", "Promises contact but the destination has no form.")

    if ptype == "PURCHASE":
        if ev.get("redirect_to_home"):
            return _r("broken", "Pricing/checkout link redirects to the homepage — no pricing shown.")
        if ev.get("has_pricing_signals"):
            return _r("honored", "Pricing content is present.")
        # We only scan links, not page prose — don't assert broken when we can't see pricing.
        return _r("unverified", "Couldn't confirm pricing content from here.")

    if ptype == "SIGNUP":
        if not has_form:
            return _r("broken", "Promises signup but the destination has no form.")
        if ev.get("anchor_says_free") and ev.get("has_payment_fields"):
            return _r("broken", "Free trial promises a card-free start but the form asks for payment details.",
                      severity="high")
        return _r("honored", "A signup form is present.")

    # ── Tier 2 ──
    if ptype == "WATCH":
        if MEDIA in ints or ev.get("has_video"):
            return _r("honored", "A video embed is present.")
        return _r("broken", "Promises a video but none is present on the destination.")

    if ptype == "CALL":
        if ev.get("is_tel"):
            return _r("honored", "A valid tel: link.")
        if ev.get("has_phone"):
            return _r("honored", "A phone number is present.")
        return _r("broken", "Promises a call but there's no tel: link or phone number.")

    if ptype == "DIRECTIONS":
        if ev.get("is_maps") or ev.get("has_address"):
            return _r("honored", "A map or address is present.")
        return _r("broken", "Promises directions but no map or address is present.")

    if ptype == "APPLY":
        if has_form or ev.get("is_ats"):
            return _r("honored", "An application form / ATS is present.")
        return _r("broken", "A careers page with no application path.")

    if ptype == "CHAT":
        if CHAT in ints:
            if ev.get("chat_healthy") is False:
                return _r("broken", "Chat promised, but the widget isn't loading.")
            return _r("honored", "A chat widget is present.")
        return _r("broken", "Promises chat but no widget is present.")

    return _r("unverified", "No verification rule for this promise type.")
