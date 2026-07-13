"""Quarterly attestation — the document procurement asks for.

Pure computation over the consent ledger. THE WORDING LAW applies: this is a
record of OBSERVED technical behavior, never a compliance determination. The
document always carries its scope statement and its coverage-honesty block
(pages enrolled vs site total, checks not performed, CMPs not operable). Honest
about mid-quarter enrollment — never claims coverage it doesn't have.

Immutable on issue: content_hash() over the canonical document is stored so the
issued PDF is verifiable and the row is never mutated.
"""
import hashlib
import json
from datetime import datetime, timezone

from consent_verdict import SCOPE_STATEMENT, ENGINE_VERSION
from consent_classify import CLASSIFICATION_VERSION

_METHODOLOGY_CHECKS = {
    "UK": ["Cold load (no interaction) — trackers firing before consent",
           "Reject path — trackers firing after the reject control is operated",
           "Accept path — baseline of intended trackers"],
    "US": ["GPC render (Sec-GPC:1) — advertising/adtech firing despite the signal",
           "Opt-out mechanism — presence and destination of a 'Do Not Sell or Share' control"],
}


def _dt(v):
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def quarter_bounds(year, q):
    start_month = (q - 1) * 3 + 1
    start = datetime(year, start_month, 1, tzinfo=timezone.utc)
    end_year, end_month = (year + 1, 1) if start_month + 3 > 12 else (year, start_month + 3)
    end = datetime(end_year, end_month, 1, tzinfo=timezone.utc)
    return start, end, f"Q{q} {year}"


def _obs_key(v):
    ev = v.get("evidence") or {}
    return (v.get("regime"), v.get("code"), ev.get("host") or "")


def compute_attestation(sessions, enrollments, period_start, period_end, now=None,
                        agency_name="Apexure", site_url="", site_total_pages=None):
    now = now or datetime.now(timezone.utc)
    start, end = period_start, period_end

    in_period = [s for s in (sessions or [])
                 if start <= (_dt(s.get("created_at")) or start) < end]
    in_period.sort(key=lambda s: s.get("created_at") or "")

    # Mid-quarter enrollment honesty: the real coverage window per page.
    enrolled_ats = [_dt(e.get("enrolled_at")) for e in (enrollments or []) if _dt(e.get("enrolled_at"))]
    earliest_enroll = min(enrolled_ats) if enrolled_ats else None
    coverage_start = max(start, earliest_enroll) if earliest_enroll else start
    prorated = bool(earliest_enroll and earliest_enroll > start)
    coverage_note = (f"Observation began {coverage_start.date().isoformat()} (mid-period). "
                     f"This attestation covers {coverage_start.date().isoformat()} to "
                     f"{end.date().isoformat()}, not the full period."
                     if prorated else "Full-period coverage.")

    regimes = {}
    evidence = []
    limitations_seen = {}
    for regime in ("UK", "US"):
        runs = [s for s in in_period if s.get("regime") == regime]
        if not runs:
            continue
        # observations table: aggregate by (code, host); first_seen + resolved
        table = {}
        for s in runs:
            at = _dt(s.get("created_at"))
            present_keys = set()
            for v in (s.get("verdicts") or []):
                if v.get("kind") == "limitation":
                    limitations_seen.setdefault(v.get("code"), v.get("statement"))
                    continue
                key = _obs_key(v)
                present_keys.add(key)
                row = table.setdefault(key, {"statement": v["statement"], "severity": v["severity"],
                                             "first_seen": at, "last_seen": at, "resolved_at": None})
                row["last_seen"] = at
            # anything previously seen but absent now → resolved at this run
            for key, row in table.items():
                if key not in present_keys and row["resolved_at"] is None and row["last_seen"] < at:
                    row["resolved_at"] = at
        observations = []
        for key, row in table.items():
            observations.append({
                "statement": row["statement"], "severity": row["severity"],
                "first_seen": row["first_seen"].date().isoformat() if row["first_seen"] else None,
                "resolved_at": row["resolved_at"].date().isoformat() if row["resolved_at"] else None,
                "status": "resolved" if row["resolved_at"] else "open",
            })
        observations.sort(key=lambda o: (o["status"] != "open", o["statement"]))
        open_n = sum(1 for o in observations if o["status"] == "open")
        summary = (f"{len(runs)} observation session(s) of the {regime} profile this period: "
                   + ("consent-gated firing consistent throughout — no observations."
                      if not observations else
                      f"{open_n} observation(s) open, {len(observations) - open_n} resolved within the period."))
        regimes[regime] = {"sessions_count": len(runs), "observations": observations, "summary": summary}
        # evidence appendix: hashed refs into the ledger
        for s in runs[:12]:
            evidence.append({"regime": regime, "mode": s.get("mode"),
                             "at": s.get("created_at"),
                             "ref_hash": hashlib.sha256((s.get("id") or "").encode()).hexdigest()[:16],
                             "requests": len(s.get("requests") or [])})

    document = {
        "scope_statement": SCOPE_STATEMENT,
        "period": {"start": start.date().isoformat(), "end": end.date().isoformat(),
                   "coverage_note": coverage_note, "prorated": prorated},
        "methodology": {
            "cadence": (enrollments[0].get("cadence") if enrollments else "weekly"),
            "engine_version": ENGINE_VERSION, "classification_version": CLASSIFICATION_VERSION,
            "checks": {r: _METHODOLOGY_CHECKS[r] for r in regimes},
        },
        "regimes": regimes,
        "evidence": evidence,
        "coverage": {
            "pages_enrolled": len(enrollments or []),
            "site_total_pages": site_total_pages,
            "checks_not_performed": _not_performed(regimes),
            "limitations": list(limitations_seen.values()),
        },
        "signoff": {"observing_party": agency_name, "issued_at": now.date().isoformat(), "site_url": site_url},
    }
    return document


def _not_performed(regimes):
    notes = []
    if "UK" not in regimes:
        notes.append("UK (PECR) profile was not observed for this site in this period.")
    if "US" not in regimes:
        notes.append("US (CCPA/CPRA) profile was not observed for this site in this period.")
    notes.append("End-to-end operation of opt-out mechanisms is not performed (existence and destination only).")
    return notes


def content_hash(document):
    """Stable hash over the canonical document — the immutability anchor."""
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
