"""Governance surfaces — drift vs continuous, diff, register copy, scope statement."""
from consent_governance import (build_governance, diff_sessions, remediation_hint,
                                soften_for_portal)
from consent_verdict import SCOPE_STATEMENT


def _obs(code, host, sev="critical", regime="US"):
    return {"kind": "observation", "regime": regime, "code": code, "severity": sev,
            "statement": f"{host} fired while the Global Privacy Control signal was present — the browser signal was not honored.",
            "citation": "CPRA treats GPC as a valid consumer opt-out-of-sale/sharing signal.",
            "evidence": {"host": host}}


def _session(page, regime, mode, verdicts, at):
    return {"page_url": page, "regime": regime, "mode": mode, "verdicts": verdicts, "created_at": at}


# ── diff ──
def test_diff_new_resolved_continuing():
    prior = [_obs("gpc_not_honored", "facebook.net")]
    curr = [_obs("gpc_not_honored", "facebook.net"), _obs("gpc_not_honored", "doubleclick.net")]
    d = diff_sessions(prior, curr)
    assert len(d["new"]) == 1 and len(d["continuing"]) == 1 and d["resolved"] == []


# ── drift (clean → failing) is an INCIDENT; failing-since-first is a FINDING ──
def test_continuous_failure_is_a_finding_not_incident():
    # present in the very first run and every run after → finding
    sessions = [
        _session("https://a.co", "US", "gpc", [_obs("gpc_not_honored", "facebook.net")], "2026-06-01T06:00:00Z"),
        _session("https://a.co", "US", "gpc", [_obs("gpc_not_honored", "facebook.net")], "2026-06-08T06:00:00Z"),
    ]
    g = build_governance(sessions)
    chk = g["regimes"]["US"]["open_checks"][0]
    assert chk["status"] == "finding" and chk["first_observed"] == "2026-06-01T06:00:00Z"


def test_new_observation_after_a_clean_run_is_an_incident():
    # clean on Jun 3, then adtech-pre-consent appears Jun 10 → incident (drift)
    sessions = [
        _session("https://a.co", "US", "gpc", [], "2026-06-03T06:00:00Z"),
        _session("https://a.co", "US", "gpc", [_obs("gpc_not_honored", "facebook.net")], "2026-06-10T06:00:00Z"),
    ]
    g = build_governance(sessions)
    chk = g["regimes"]["US"]["open_checks"][0]
    assert chk["status"] == "incident" and chk["first_observed"] == "2026-06-10T06:00:00Z"


# ── verdict-first header + register separation ──
def test_all_clear_header_is_the_hero():
    g = build_governance([_session("https://a.co", "US", "gpc", [], "2026-06-10T06:00:00Z")])
    assert g["regimes"]["US"]["all_clear"] is True
    assert "honored" in g["regimes"]["US"]["header"]


def test_header_names_the_observation():
    g = build_governance([_session("https://a.co", "UK", "cold",
                          [{"kind": "observation", "regime": "UK", "code": "pre_consent_fire", "severity": "critical",
                            "statement": "Meta advertising pixel fired before any consent was given.",
                            "citation": "UK PECR requires consent before non-essential trackers are set.",
                            "evidence": {"host": "facebook.net"}}], "2026-06-10T06:00:00Z")])
    h = g["regimes"]["UK"]["header"]
    assert h.startswith("UK profile:") and "before any consent" in h


def test_portal_softening_changes_operator_wording():
    agency = "UK profile: 2 observations open — a pixel fires before consent."
    assert "items we're tracking" in soften_for_portal(agency)


# ── remediation is technical, not legal ──
def test_remediation_is_a_technical_suggestion():
    r = remediation_hint("gpc_not_honored")
    assert r["kind"] == "technical_suggestion"
    for legal in ("compliant", "lawful", "you must", "illegal"):
        assert legal not in r["text"].lower()


# ── the wording law: scope statement present on the surface payload ──
def test_scope_statement_present_on_governance_payload():
    g = build_governance([_session("https://a.co", "US", "gpc", [], "2026-06-10T06:00:00Z")])
    assert g["scope_statement"] == SCOPE_STATEMENT
