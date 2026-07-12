"""The tracer pipeline — every outcome branch + every safety gate, mocked.
No network, no browser, no real CRM: submit_fn and connector are injected."""
import asyncio

import pytest

import tracer
from tracer import (run_tracer, verify_arrival, build_payload, default_test_email,
                    TracerRefused)

TOK = "tok123"
TEST_EMAIL = "qa+linkspy-tracer@apexure.com"

CONTRACT = {
    "id": "c1", "version": 2, "site_id": "s1",
    "form_ref": {"page_url": "https://x.com/contact", "selector": "#f"},
    "fields": [
        {"name": "email", "kind": "visible", "expected_crm_property": "email"},
        {"name": "firstname", "kind": "visible", "expected_crm_property": "firstname"},
        {"name": "gclid", "kind": "hidden", "expected_crm_property": None},
    ],
}
ENROLLED = {"enabled": True, "acknowledged": True, "test_email": TEST_EMAIL, "marker_field": None}


class MockConnector:
    def __init__(self, contact=None, delete_ok=True):
        self.contact, self.delete_ok, self.deleted = contact, delete_ok, []

    async def search_contact(self, email):
        return self.contact

    async def delete_contact(self, cid):
        self.deleted.append(cid)
        return self.delete_ok


class Submitter:
    def __init__(self, submitted=True, raises=False):
        self.submitted, self.raises, self.calls = submitted, raises, 0

    async def __call__(self, *, url, selector, payload):
        self.calls += 1
        if self.raises:
            raise RuntimeError("browser crashed")
        return {"submitted": self.submitted, "status": 200, "screenshot_ref": "ev1"}


def _contact(props):
    return {"id": "hs-42", "properties": props}


def _run(**kw):
    return asyncio.run(run_tracer(**kw))


# ── pure logic ──
def test_verify_arrival_all_match_is_verified():
    payload = {"email": TEST_EMAIL, "firstname": "LINKSPY-TEST-tok123"}
    props = {"email": TEST_EMAIL, "firstname": "LINKSPY-TEST-tok123"}
    arrival, outcome = verify_arrival(CONTRACT, payload, props)
    assert outcome == "verified"
    assert all(a["arrived"] and a["arrived_value_matches"] for a in arrival)
    assert {a["field"] for a in arrival} == {"email", "firstname"}   # hidden gclid unmapped


def test_verify_arrival_missing_field_is_partial():
    payload = {"email": TEST_EMAIL, "firstname": "LINKSPY-TEST-tok123"}
    props = {"email": TEST_EMAIL}   # firstname never arrived
    arrival, outcome = verify_arrival(CONTRACT, payload, props)
    assert outcome == "partial"
    fn = next(a for a in arrival if a["field"] == "firstname")
    assert fn["arrived"] is False


def test_build_payload_skips_hidden_and_puts_email():
    p = build_payload(CONTRACT, TEST_EMAIL, TOK)
    assert p["email"] == TEST_EMAIL
    assert "gclid" not in p                      # hidden never filled
    assert p["firstname"].startswith("LINKSPY-TEST")


def test_default_test_email_is_unmistakably_flagged():
    assert "linkspy-tracer" in default_test_email("apexure.com")


# ── happy path ──
def test_verified_run_is_silent_and_cleans_up(monkeypatch):
    monkeypatch.setenv("TRACER_ENABLED", "1")
    conn = MockConnector(_contact({"email": TEST_EMAIL, "firstname": "LINKSPY-TEST"}))
    sub = Submitter(submitted=True)
    out = _run(contract=CONTRACT, enrollment=ENROLLED, connector=conn, submit_fn=sub,
               run_token=TOK, mode="scheduled")
    assert out["row"]["outcome"] == "verified"
    assert out["row"]["cleanup"] == "done"
    assert out["needs_alert"] is False
    assert conn.deleted == ["hs-42"]             # contact removed
    assert sub.calls == 1                         # exactly once


# ── every failure branch writes a complete ledger row ──
def test_partial_arrival_alerts(monkeypatch):
    monkeypatch.setenv("TRACER_ENABLED", "1")
    conn = MockConnector(_contact({"email": TEST_EMAIL}))   # firstname missing
    out = _run(contract=CONTRACT, enrollment=ENROLLED, connector=conn, submit_fn=Submitter(),
               run_token=TOK)
    assert out["row"]["outcome"] == "partial" and out["needs_alert"] is True
    assert conn.deleted == ["hs-42"]             # still cleaned up


def test_failed_submit_never_reaches_crm(monkeypatch):
    monkeypatch.setenv("TRACER_ENABLED", "1")
    conn = MockConnector(_contact({"email": TEST_EMAIL}))
    out = _run(contract=CONTRACT, enrollment=ENROLLED, connector=conn,
               submit_fn=Submitter(submitted=False), run_token=TOK)
    assert out["row"]["outcome"] == "failed_submit"
    assert out["row"]["crm_contact_ref"] is None
    assert conn.deleted == []


def test_submit_exception_is_failed_submit(monkeypatch):
    monkeypatch.setenv("TRACER_ENABLED", "1")
    out = _run(contract=CONTRACT, enrollment=ENROLLED, connector=MockConnector(),
               submit_fn=Submitter(raises=True), run_token=TOK)
    assert out["row"]["outcome"] == "failed_submit"


def test_failed_arrival_when_contact_never_appears(monkeypatch):
    monkeypatch.setenv("TRACER_ENABLED", "1")
    out = _run(contract=CONTRACT, enrollment=ENROLLED, connector=MockConnector(contact=None),
               submit_fn=Submitter(), run_token=TOK, max_polls=3)
    assert out["row"]["outcome"] == "failed_arrival" and out["needs_alert"] is True


def test_failed_cleanup_is_loud(monkeypatch):
    monkeypatch.setenv("TRACER_ENABLED", "1")
    conn = MockConnector(_contact({"email": TEST_EMAIL, "firstname": "LINKSPY-TEST"}), delete_ok=False)
    out = _run(contract=CONTRACT, enrollment=ENROLLED, connector=conn, submit_fn=Submitter(), run_token=TOK)
    assert out["row"]["cleanup"] == "failed"
    assert out["alert_kind"] == "failed_cleanup" and out["needs_alert"] is True


def test_ledger_row_is_complete_every_branch(monkeypatch):
    monkeypatch.setenv("TRACER_ENABLED", "1")
    conn = MockConnector(_contact({"email": TEST_EMAIL, "firstname": "LINKSPY-TEST"}))
    row = _run(contract=CONTRACT, enrollment=ENROLLED, connector=conn, submit_fn=Submitter(), run_token=TOK)["row"]
    for key in ("contract_id", "contract_version", "site_id", "mode", "outcome",
                "submitted_payload_hash", "arrival", "cleanup", "evidence"):
        assert key in row


# ── the hard safety gates: NO path to submit ──
def test_flag_off_refuses_and_never_submits(monkeypatch):
    monkeypatch.delenv("TRACER_ENABLED", raising=False)
    sub = Submitter()
    with pytest.raises(TracerRefused):
        _run(contract=CONTRACT, enrollment=ENROLLED, connector=MockConnector(), submit_fn=sub)
    assert sub.calls == 0


def test_unenrolled_refuses_and_never_submits(monkeypatch):
    monkeypatch.setenv("TRACER_ENABLED", "1")
    sub = Submitter()
    with pytest.raises(TracerRefused):
        _run(contract=CONTRACT, enrollment={"enabled": False, "acknowledged": True, "test_email": TEST_EMAIL},
             connector=MockConnector(), submit_fn=sub)
    assert sub.calls == 0


def test_missing_acknowledgment_refuses(monkeypatch):
    monkeypatch.setenv("TRACER_ENABLED", "1")
    sub = Submitter()
    with pytest.raises(TracerRefused):
        _run(contract=CONTRACT, enrollment={"enabled": True, "acknowledged": False, "test_email": TEST_EMAIL},
             connector=MockConnector(), submit_fn=sub)
    assert sub.calls == 0


def test_payment_form_refused_and_never_submits(monkeypatch):
    monkeypatch.setenv("TRACER_ENABLED", "1")
    pay = {**CONTRACT, "fields": CONTRACT["fields"] + [{"name": "cardNumber", "kind": "visible"}]}
    sub = Submitter()
    with pytest.raises(TracerRefused):
        _run(contract=pay, enrollment=ENROLLED, connector=MockConnector(), submit_fn=sub)
    assert sub.calls == 0


# ── the stamp (consecutive-green) ──
def test_stamp_consecutive_green_counts_verified_days():
    from tracer import stamp_summary
    runs = [
        {"started_at": "2026-07-12T06:02:00Z", "outcome": "verified"},
        {"started_at": "2026-07-11T06:01:00Z", "outcome": "verified"},
        {"started_at": "2026-07-10T06:03:00Z", "outcome": "verified"},
    ]
    s = stamp_summary(runs)
    assert s["state"] == "verified" and s["consecutive_days"] == 3


def test_stamp_breakage_flips_state_and_stops_streak():
    from tracer import stamp_summary
    runs = [
        {"started_at": "2026-07-12T06:02:00Z", "outcome": "partial"},
        {"started_at": "2026-07-11T06:01:00Z", "outcome": "verified"},
    ]
    s = stamp_summary(runs)
    assert s["state"] == "broken" and s["consecutive_days"] == 0
    assert s["broken_since"] is not None


def test_stamp_none_when_no_runs():
    from tracer import stamp_summary
    assert stamp_summary([])["state"] == "none"
