"""Consent engine — classification, verdicts, the wording law, CMP table."""
import pathlib

from consent_classify import (consent_class, classification_table, is_non_essential,
                              ESSENTIAL, ANALYTICS_C, ADTECH, FUNCTIONAL, UNKNOWN)
from consent_verdict import uk_verdicts, us_verdicts, SCOPE_STATEMENT, scope_statement
from consent_cmp import detect_cmp_in_html, adapter_for, is_reject_text


# ── classification + provenance ──
def test_adtech_class_with_named_provenance():
    c = consent_class("connect.facebook.net", "https://connect.facebook.net/fbevents.js")
    assert c["class"] == ADTECH and "Meta" in c["provenance"]


def test_analytics_and_essential_and_functional():
    assert consent_class("google-analytics.com")["class"] == ANALYTICS_C
    assert consent_class("fonts.gstatic.com")["class"] == ESSENTIAL
    assert consent_class("calendly.com")["class"] == FUNCTIONAL


def test_first_party_is_essential():
    c = consent_class("shop.acme.com", site_host="acme.com")
    assert c["class"] == ESSENTIAL and c["source"] == "own-domain"


def test_unknown_host_is_a_limitation_not_a_guess():
    assert consent_class("weird-unknown-host-xyz.com")["class"] == UNKNOWN


def test_every_table_rule_carries_provenance():
    t = classification_table()
    assert t["version"] >= 1
    assert all(r["provenance"] for r in t["rules"])   # auditability of the table itself


# ── the wording law (asserted as a string, everywhere) ──
def test_scope_statement_is_the_exact_fixed_string():
    assert SCOPE_STATEMENT == ("Technical observation of tracking behavior. Not legal advice; "
                               "consult counsel for compliance determinations.")
    assert scope_statement() == SCOPE_STATEMENT


def test_no_compliance_language_in_any_verdict_output():
    # Run the full matrix and assert every produced statement/citation is
    # observational — never a legal-compliance verdict.
    outputs = []
    outputs += uk_verdicts([_req("connect.facebook.net", ADTECH)],
                           [_req("connect.facebook.net", ADTECH)],
                           cmp={"detected": True, "operated": True, "accept_clicks": 1, "reject_clicks": 3})
    outputs += uk_verdicts([], [], cmp={"detected": False})
    outputs += us_verdicts([_req("doubleclick.net", ADTECH)], optout={"found": False})
    outputs += us_verdicts([], optout={"found": True, "resolves": False})
    forbidden = ("compliant", "non-compliant", "violation of law", "illegal", "lawful", "unlawful", "you must")
    for o in outputs:
        text = f"{o['statement']} {o['citation']}".lower()
        assert not any(f in text for f in forbidden), f"forbidden wording in: {o}"


# ── UK verdict matrix ──
def _req(host, cls, ms=100, url=""):
    return {"host": host, "consent_class": cls, "ms_after_load": ms, "url": url or f"https://{host}/x"}


def test_uk_pre_consent_adtech_is_critical_observation():
    obs = uk_verdicts([_req("connect.facebook.net", ADTECH)], [], cmp={"detected": True, "operated": True})
    fire = [o for o in obs if o["code"] == "pre_consent_fire"]
    assert fire and fire[0]["severity"] == "critical"
    assert "fired before any consent" in fire[0]["statement"]        # observational wording
    assert fire[0]["kind"] == "observation"


def test_uk_post_reject_fire_is_critical():
    obs = uk_verdicts([], [_req("connect.facebook.net", ADTECH)],
                      cmp={"detected": True, "operated": True})
    assert any(o["code"] == "post_reject_fire" and o["severity"] == "critical" for o in obs)


def test_uk_undetected_cmp_is_a_declared_limitation_never_a_verdict():
    obs = uk_verdicts([_req("google-analytics.com", ANALYTICS_C)], [], cmp={"detected": False})
    lim = [o for o in obs if o["kind"] == "limitation"]
    assert lim and lim[0]["code"] == "cmp_undetected"
    # no reject-path verdict was invented
    assert not any(o["code"] == "post_reject_fire" for o in obs)


def test_uk_reject_harder_than_accept():
    obs = uk_verdicts([], [], cmp={"detected": True, "operated": True, "accept_clicks": 1, "reject_clicks": 3})
    assert any(o["code"] == "reject_harder" for o in obs)


# ── US verdict matrix ──
def test_us_gpc_not_honored_is_critical():
    obs = us_verdicts([_req("doubleclick.net", ADTECH)], optout={"found": True, "resolves": True, "mechanism_present": True})
    g = [o for o in obs if o["code"] == "gpc_not_honored"]
    assert g and g[0]["severity"] == "critical" and "not honored" in g[0]["statement"]


def test_us_missing_and_dead_optout():
    assert any(o["code"] == "optout_missing" for o in us_verdicts([], optout={"found": False}))
    assert any(o["code"] == "optout_dead" for o in us_verdicts([], optout={"found": True, "resolves": False}))


def test_us_gpc_honored_produces_no_observation():
    # only essential/analytics fired under GPC (no adtech) + working opt-out → clean
    obs = us_verdicts([_req("fonts.gstatic.com", ESSENTIAL)],
                      optout={"found": True, "resolves": True, "mechanism_present": True})
    assert obs == []


# ── CMP adapter table ──
def test_cmp_detection_named_and_generic_and_none():
    assert detect_cmp_in_html("<div id='onetrust-banner-sdk'>Cookie consent</div>") == "OneTrust"
    assert detect_cmp_in_html("<div class='cky-consent-container'>cookies</div>") == "CookieYes"
    assert detect_cmp_in_html("<div>We use cookies. Reject all</div>") == "generic"
    assert detect_cmp_in_html("<div>Welcome to our site</div>") is None


def test_adapter_has_reject_and_accept_selectors():
    a = adapter_for("OneTrust")
    assert a["reject"] and a["accept"]
    assert is_reject_text("Reject All") and not is_reject_text("Accept All")
