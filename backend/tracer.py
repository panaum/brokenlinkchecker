"""The tracer: submit a flagged test lead, verify field-by-field arrival in the
CRM, delete it, and write ONE complete immutable ledger row — every branch.

Safety is layered and none of it is optional (inherits the active-submission
rails + adds its own):
  • TRACER_ENABLED flag, default OFF — its own switch, separate from active testing.
  • Per-form enrollment + a typed acknowledgment before anything is ever sent.
  • Payment forms are refused (reuses is_payment_form). Hidden/honeypot fields
    are never filled. Exactly ONE submission per run.
  • Cleanup is mandatory: the created contact is deleted; a failed delete is a
    LOUD outcome (failed_cleanup), never silently dropped.

The pipeline is fully injectable (connector + submit_fn) so every outcome branch
is unit-tested without a network or a real CRM.
"""
import hashlib
import os

from active_submission import TEST_VALUE, is_payment_form, is_honeypot

TRACER_ENABLED_FLAG = "TRACER_ENABLED"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def tracer_enabled() -> bool:
    return os.getenv(TRACER_ENABLED_FLAG, "").strip().lower() in _TRUTHY


def _get(o, k, default=None):
    return o.get(k, default) if isinstance(o, dict) else getattr(o, k, default)


def _hash(v) -> str:
    return hashlib.sha256(str(v if v is not None else "").encode("utf-8", "ignore")).hexdigest()[:16]


def default_test_email(agency_domain="apexure.com", token="") -> str:
    tag = f"+linkspy-tracer{('-' + token) if token else ''}"
    return f"qa{tag}@{agency_domain}"


class TracerRefused(Exception):
    """A safety gate blocked the run BEFORE any submission. Never a soft error."""


def _norm(v):
    return str(v if v is not None else "").strip().lower()


def build_payload(contract, test_email, run_token, marker_field=None):
    """Field → value for the ONE submission. Only visible, non-honeypot,
    non-payment fields are filled; the tracer email goes in the email field, and
    the flagged marker (with the run token for correlation) elsewhere. Hidden
    fields are never filled (they are JS/URL populated).

    The fill marker is the fixed TEST_VALUE — matching what the reused executor
    (submit_test_form) actually writes — so sent and received compare cleanly.
    The per-run token lives in the ledger evidence for correlation, not in a
    submitted field."""
    marker = TEST_VALUE
    payload = {}
    for f in _get(contract, "fields") or []:
        name = (_get(f, "name") or "").strip()
        if not name:
            continue
        if _get(f, "kind") == "hidden":
            continue                     # never fill hidden/tracking inputs
        if is_honeypot(f):
            continue
        prop = _get(f, "expected_crm_property")
        if prop == "email" or "email" in name.lower():
            payload[name] = test_email
        elif prop == "phone" or "phone" in name.lower():
            payload[name] = "+10000000000"
        elif name == marker_field:
            payload[name] = marker
        else:
            payload[name] = marker
    return payload


def verify_arrival(contract, payload, crm_properties):
    """Pure field-by-field check of what the CRM received vs what we sent.
    Returns (arrival[], outcome) where outcome ∈ verified|partial (arrival is
    only meaningful once a contact was found)."""
    crm = crm_properties or {}
    arrival = []
    mapped = 0
    ok = 0
    for f in _get(contract, "fields") or []:
        prop = _get(f, "expected_crm_property")
        name = (_get(f, "name") or "").strip()
        if not prop or not name:
            continue
        mapped += 1
        sent = payload.get(name)
        got = crm.get(prop)
        arrived = got is not None and str(got).strip() != ""
        matches = arrived and _norm(got) == _norm(sent)
        if matches:
            ok += 1
        arrival.append({
            "field": name, "crm_property": prop,
            "sent_value_hash": _hash(sent),
            "arrived": bool(arrived),
            "arrived_value_matches": bool(matches),
        })
    outcome = "verified" if (mapped > 0 and ok == mapped) else "partial"
    return arrival, outcome


def _payload_hash(payload):
    items = "&".join(f"{k}={payload[k]}" for k in sorted(payload))
    return hashlib.sha256(items.encode("utf-8", "ignore")).hexdigest()


async def run_tracer(*, contract, enrollment, connector, submit_fn, mode="scheduled",
                     run_token="run", started_at=None, max_polls=1):
    """Execute one tracer run and return a COMPLETE ledger row dict (every
    branch) plus {needs_alert, alert_kind}.

    Hard gates raise TracerRefused BEFORE any submission. `submit_fn` and
    `connector` are injected (mocked in tests) — this function never imports a
    browser or a network client itself.
    """
    # ── Safety gates — no submission may happen unless ALL pass ──
    if not tracer_enabled():
        raise TracerRefused("TRACER_ENABLED is off")
    if not _get(enrollment, "enabled"):
        raise TracerRefused("this form is not enrolled")
    if not _get(enrollment, "acknowledged"):
        raise TracerRefused("automation-exclusion acknowledgment missing")
    is_pay, reason = is_payment_form(_get(contract, "fields") or [])
    if is_pay:
        raise TracerRefused(f"payment form refused: {reason}")

    test_email = _get(enrollment, "test_email") or default_test_email(token=run_token)
    payload = build_payload(contract, test_email, run_token, _get(enrollment, "marker_field"))
    form_ref = _get(contract, "form_ref") or {}
    row = {
        "contract_id": _get(contract, "id"),
        "contract_version": _get(contract, "version") or 1,
        "site_id": _get(contract, "site_id"),
        "mode": mode,
        "submitted_payload_hash": _payload_hash(payload),
        "arrival": [],
        "crm_contact_ref": None,
        "cleanup": "done",           # nothing to clean unless a contact is created
        "evidence": {"test_email": test_email, "run_token": run_token, "field_count": len(payload)},
    }
    if started_at:
        row["started_at"] = started_at

    # ── Submit exactly once ──
    try:
        result = await submit_fn(url=form_ref.get("page_url", ""),
                                 selector=form_ref.get("selector", ""), payload=payload)
    except Exception as e:
        row.update(outcome="failed_submit", evidence={**row["evidence"], "error": str(e)[:300]})
        return {"row": row, "needs_alert": True, "alert_kind": "failed_submit"}
    row["evidence"]["submit"] = {"submitted": bool(_get(result, "submitted")),
                                 "status": _get(result, "status"),
                                 "screenshot_ref": _get(result, "screenshot_ref")}
    if not _get(result, "submitted"):
        row["outcome"] = "failed_submit"
        return {"row": row, "needs_alert": True, "alert_kind": "failed_submit"}

    # ── Poll the CRM for the tracer contact ──
    contact = None
    for _ in range(max(1, max_polls)):
        contact = await connector.search_contact(test_email)
        if contact:
            break
    if not contact:
        row["outcome"] = "failed_arrival"
        return {"row": row, "needs_alert": True, "alert_kind": "failed_arrival"}

    row["crm_contact_ref"] = _get(contact, "id")
    arrival, outcome = verify_arrival(contract, payload, _get(contact, "properties") or {})
    row["arrival"] = arrival
    row["outcome"] = outcome

    # ── Cleanup is mandatory ──
    try:
        deleted = await connector.delete_contact(_get(contact, "id"))
    except Exception as e:
        deleted = False
        row["evidence"]["cleanup_error"] = str(e)[:300]
    if deleted:
        row["cleanup"] = "done"
    else:
        row["cleanup"] = "failed"
        return {"row": row, "needs_alert": True, "alert_kind": "failed_cleanup"}

    needs_alert = outcome != "verified"
    return {"row": row, "needs_alert": needs_alert, "alert_kind": (None if outcome == "verified" else "partial")}


# ─── The stamp: the primary surface. Consecutive-green is the hero number. ──
def _date_of(iso):
    from datetime import datetime, timezone
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        return d.date()
    except Exception:
        return None


def stamp_summary(runs, now=None):
    """From ledger rows (newest-first) → the stamp. Pure.
    A day is green iff it had ≥1 run and every run that day verified."""
    runs = [r for r in (runs or []) if _get(r, "started_at")]
    if not runs:
        return {"state": "none", "consecutive_days": 0, "last_run_at": None,
                "last_verified_at": None, "broken_since": None}
    runs = sorted(runs, key=lambda r: _get(r, "started_at"), reverse=True)
    latest = runs[0]
    state = "verified" if _get(latest, "outcome") == "verified" else "broken"
    last_verified_at = next((_get(r, "started_at") for r in runs if _get(r, "outcome") == "verified"), None)

    # group by UTC date, newest date first
    by_day = {}
    for r in runs:
        d = _date_of(_get(r, "started_at"))
        if d:
            by_day.setdefault(d, []).append(r)
    streak = 0
    for d in sorted(by_day, reverse=True):
        if all(_get(r, "outcome") == "verified" for r in by_day[d]):
            streak += 1
        else:
            break

    broken_since = None
    if state == "broken":
        # earliest run in the current unbroken run of non-verified latest results
        broken_since = _get(latest, "started_at")
        for r in runs:
            if _get(r, "outcome") == "verified":
                break
            broken_since = _get(r, "started_at")
    return {
        "state": state,
        "consecutive_days": streak,
        "last_run_at": _get(latest, "started_at"),
        "last_verified_at": last_verified_at,
        "last_outcome": _get(latest, "outcome"),
        "broken_since": broken_since,
    }
