"""Quarterly attestation — windowing, proration honesty, hash immutability."""
from datetime import datetime, timezone

from attestation import quarter_bounds, compute_attestation, content_hash
from consent_verdict import SCOPE_STATEMENT


def _session(regime, mode, verdicts, at, sid="s"):
    return {"id": sid, "regime": regime, "mode": mode, "verdicts": verdicts,
            "created_at": at, "requests": [{"host": "x"}]}


def _obs(statement="Meta pixel fired before any consent was given.", host="facebook.net", sev="critical", regime="UK"):
    return {"kind": "observation", "regime": regime, "code": "pre_consent_fire", "severity": sev,
            "statement": statement, "citation": "UK PECR requires consent before non-essential trackers are set.",
            "evidence": {"host": host}}


Q2_START, Q2_END, _ = quarter_bounds(2026, 2)   # Apr 1 – Jul 1


def test_quarter_bounds():
    s, e, label = quarter_bounds(2026, 2)
    assert s.month == 4 and e.month == 7 and label == "Q2 2026"
    _, e4, _ = quarter_bounds(2026, 4)
    assert e4.year == 2027 and e4.month == 1        # Q4 rolls into next year


def test_windowing_excludes_out_of_period_sessions():
    sessions = [
        _session("UK", "cold", [], "2026-03-15T06:00:00Z"),   # before Q2
        _session("UK", "cold", [_obs()], "2026-05-10T06:00:00Z"),  # in Q2
        _session("UK", "cold", [], "2026-08-01T06:00:00Z"),   # after Q2
    ]
    doc = compute_attestation(sessions, [{"page_url": "https://a.co", "regime": "UK", "enrolled_at": "2026-04-01T00:00:00Z"}],
                              Q2_START, Q2_END)
    assert doc["regimes"]["UK"]["sessions_count"] == 1


def test_mid_quarter_enrollment_is_prorated_honestly():
    sessions = [_session("UK", "cold", [], "2026-06-15T06:00:00Z")]
    doc = compute_attestation(sessions, [{"page_url": "https://a.co", "regime": "UK", "enrolled_at": "2026-06-12T00:00:00Z"}],
                              Q2_START, Q2_END)
    assert doc["period"]["prorated"] is True
    assert "2026-06-12" in doc["period"]["coverage_note"] and "not the full period" in doc["period"]["coverage_note"]


def test_observations_table_open_and_resolved():
    sessions = [
        _session("UK", "cold", [_obs()], "2026-05-01T06:00:00Z", sid="a"),
        _session("UK", "cold", [_obs()], "2026-05-08T06:00:00Z", sid="b"),
        _session("UK", "cold", [], "2026-05-15T06:00:00Z", sid="c"),     # resolved here
    ]
    doc = compute_attestation(sessions, [{"regime": "UK", "enrolled_at": "2026-04-01T00:00:00Z"}], Q2_START, Q2_END)
    obs = doc["regimes"]["UK"]["observations"][0]
    assert obs["status"] == "resolved" and obs["first_seen"] == "2026-05-01" and obs["resolved_at"] == "2026-05-15"


def test_scope_statement_and_coverage_block_always_present():
    doc = compute_attestation([_session("UK", "cold", [], "2026-05-01T06:00:00Z")],
                              [{"regime": "UK", "enrolled_at": "2026-04-01T00:00:00Z"}], Q2_START, Q2_END)
    assert doc["scope_statement"] == SCOPE_STATEMENT
    assert "coverage" in doc and "limitations" in doc["coverage"]
    assert doc["coverage"]["checks_not_performed"]     # honesty block is never empty


def test_declared_limitations_carried_verbatim():
    lim = {"kind": "limitation", "regime": "UK", "code": "cmp_undetected",
           "statement": "No consent banner could be identified on this page; the reject-path behaviour was not observed."}
    doc = compute_attestation([_session("UK", "reject", [lim], "2026-05-01T06:00:00Z")],
                              [{"regime": "UK", "enrolled_at": "2026-04-01T00:00:00Z"}], Q2_START, Q2_END)
    assert lim["statement"] in doc["coverage"]["limitations"]


def test_white_label_signoff():
    doc = compute_attestation([_session("US", "gpc", [], "2026-05-01T06:00:00Z")],
                              [{"regime": "US", "enrolled_at": "2026-04-01T00:00:00Z"}], Q2_START, Q2_END,
                              agency_name="Northgate Digital")
    assert doc["signoff"]["observing_party"] == "Northgate Digital"


def test_content_hash_is_stable_and_change_sensitive():
    doc = compute_attestation([_session("UK", "cold", [], "2026-05-01T06:00:00Z")],
                              [{"regime": "UK", "enrolled_at": "2026-04-01T00:00:00Z"}], Q2_START, Q2_END)
    h1 = content_hash(doc)
    assert h1 == content_hash(dict(doc))          # stable
    tampered = {**doc, "signoff": {**doc["signoff"], "observing_party": "Someone Else"}}
    assert content_hash(tampered) != h1           # any change moves the hash
