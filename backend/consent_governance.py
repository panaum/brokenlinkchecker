"""Governance surfaces — turn the consent ledger into a verdict-first summary,
distinguish DRIFT (a newly-appearing observation) from a CONTINUOUS finding, and
offer TECHNICAL (never legal) remediation hints.

Pure + deterministic. Reads ledger sessions; never renders a legal conclusion —
the wording law from consent_verdict applies here too.
"""
from consent_verdict import SCOPE_STATEMENT

# ── Remediation playbook: authored TECHNICAL suggestions keyed by observation
#    code (+ a note that they are technical, not legal, advice). ──
_REMEDIATION = {
    "pre_consent_fire": "This tag fires on page load, before the consent banner. Load it through your CMP/GTM behind a consent trigger so it waits for opt-in.",
    "post_reject_fire": "The tag still fires after reject — its consent trigger isn't wired to the CMP's 'reject' event. Gate it on the CMP's consent state, not just page load.",
    "reject_harder": "Reject takes more clicks than accept. Enable a top-level 'Reject All' button in your CMP configuration so both are one click.",
    "gpc_not_honored": "This pixel loads via a direct script tag, outside the CMP's control — move it under GTM with consent-mode triggers so the Global Privacy Control signal gates it.",
    "optout_missing": "No 'Do Not Sell or Share'-class link was found. Add one linking to your CMP's US-privacy panel or an opt-out request form.",
    "optout_dead": "The opt-out link is broken. Point it at a working CMP panel or request form.",
    "optout_no_mechanism": "The opt-out link resolves but its destination has no operable form or panel. Ensure it renders a real opt-out mechanism.",
}


def remediation_hint(code):
    hint = _REMEDIATION.get(code)
    if not hint:
        return None
    return {"text": hint, "kind": "technical_suggestion"}


def _observations(session):
    return [v for v in (session.get("verdicts") or []) if v.get("kind") == "observation"]


def _group_key(v):
    # a "check" is identified by regime + code + the specific host (so two pixels
    # are two checks, but the same pixel across weeks is one check).
    ev = v.get("evidence") or {}
    return (v.get("regime"), v.get("code"), ev.get("host") or "")


def diff_sessions(prior_verdicts, current_verdicts):
    """New / resolved / continuing observations between two runs of the same
    page+regime."""
    prior = {_group_key(v) for v in (prior_verdicts or []) if v.get("kind") == "observation"}
    curr = {_group_key(v) for v in (current_verdicts or []) if v.get("kind") == "observation"}
    return {"new": sorted(curr - prior), "resolved": sorted(prior - curr),
            "continuing": sorted(curr & prior)}


def build_governance(sessions):
    """sessions: all consent_sessions for a site (dicts, any order). Returns the
    verdict-first governance summary per regime, each check classified as an
    incident (drift), a finding (continuous since first observed), or resolved."""
    # sessions that carry verdicts, grouped by (page_url, regime), time-ordered
    carriers = [s for s in sessions if (s.get("verdicts"))]
    by_pr = {}
    for s in sessions:
        by_pr.setdefault((s.get("page_url"), s.get("regime")), []).append(s)
    for k in by_pr:
        by_pr[k].sort(key=lambda s: s.get("created_at") or "")

    regimes = {}
    for (page_url, regime), runs in by_pr.items():
        verdict_runs = [r for r in runs if r.get("verdicts") is not None]
        if not verdict_runs:
            continue
        latest = verdict_runs[-1]
        current_obs = _observations(latest)
        # first-observed + drift classification per current observation
        checks = []
        for v in current_obs:
            key = _group_key(v)
            first_seen = None
            had_clean_then_fail = False
            was_present = None
            drift_from = None
            prev_at = None
            for i, r in enumerate(verdict_runs):
                present = key in {_group_key(x) for x in _observations(r)}
                if present and first_seen is None:
                    first_seen = r.get("created_at")
                if was_present is False and present:
                    had_clean_then_fail = True   # a clean run, then this appeared → drift
                    drift_from = drift_from or prev_at
                was_present = present
                prev_at = r.get("created_at")
            status = "incident" if had_clean_then_fail else "finding"
            checks.append({
                "code": v["code"], "regime": regime, "severity": v["severity"],
                "statement": v["statement"], "citation": v["citation"],
                "evidence": v.get("evidence") or {}, "first_observed": first_seen,
                "status": status, "page_url": page_url, "drift_from": drift_from,
                "remediation": remediation_hint(v["code"]),
            })
        limitations = [v for v in (latest.get("verdicts") or []) if v.get("kind") == "limitation"]
        r = regimes.setdefault(regime, {"open_checks": [], "limitations": [], "pages": 0})
        r["open_checks"].extend(checks)
        r["limitations"].extend(limitations)
        r["pages"] += 1

    for regime, r in regimes.items():
        r["header"] = _header(regime, r["open_checks"], r["limitations"])
        r["all_clear"] = len(r["open_checks"]) == 0
    return {"scope_statement": SCOPE_STATEMENT, "regimes": regimes}


def _header(regime, checks, limitations):
    """Verdict-first, plain-English, agency register (portal softens separately)."""
    n = len(checks)
    if regime == "UK":
        if n == 0:
            base = "UK profile: no observations — non-essential trackers were not seen firing before consent."
        else:
            top = min(checks, key=lambda c: {"critical": 0, "high": 1, "medium": 2}.get(c["severity"], 3))
            base = f"UK profile: {n} observation{'s' if n != 1 else ''} open — {top['statement'].rstrip('.').lower()}."
    else:  # US
        if n == 0:
            base = "US profile: the GPC signal was honored and an opt-out mechanism was present."
        else:
            top = min(checks, key=lambda c: {"critical": 0, "high": 1, "medium": 2}.get(c["severity"], 3))
            base = f"US profile: {n} observation{'s' if n != 1 else ''} open — {top['statement'].rstrip('.').lower()}."
    return base


def soften_for_portal(header):
    """Portal register: same facts, gentler framing, no operator verbs."""
    return (header
            .replace("observation open", "item we're tracking")
            .replace("observations open", "items we're tracking"))
