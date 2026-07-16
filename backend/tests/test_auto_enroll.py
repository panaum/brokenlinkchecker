"""Part A — qa.completed → weekly auto-enroll: only when flag on + site
unmonitored; never downgrades; timeline written; flag-off byte-identical."""
import json
import time

import pytest
from fastapi.testclient import TestClient

import main
import database
import spine
from spine_contract import sign, SPINE_SIG_HEADER, SPINE_SENT_AT_HEADER, EVENT_TYPES

client = TestClient(main.app)
SECRET = "test-secret"

COMPLETED = {"id": "c1", "type": EVENT_TYPES["QA_COMPLETED"], "schema_version": 1,
             "occurred_at": "2026-07-16T00:00:00Z", "producer": "qa",
             "registry_deliverable_id": "d1", "registry_site_id": "s1",
             "payload": {"qa_page_ref": "p1", "checklist_summary": {"passed": 3, "failed": 0, "na": 1}}}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SPINE_SECRET", SECRET)
    monkeypatch.delenv("SPINE_CONSUME", raising=False)
    monkeypatch.delenv("AUTO_ENROLL", raising=False)

    async def ins(e, t, p):
        return {"duplicate": False}
    async def noop(*a, **k):
        return None
    monkeypatch.setattr(database, "spine_inbox_insert", ins)
    monkeypatch.setattr(database, "spine_inbox_mark", noop)
    monkeypatch.setattr(database, "timeline_add", noop)
    monkeypatch.setattr(database, "spine_marker_set", noop)


def _post(env, secret=SECRET):
    raw = json.dumps(env)
    return client.post("/api/spine/inbox", content=raw, headers={
        SPINE_SIG_HEADER: sign(raw, secret), SPINE_SENT_AT_HEADER: str(int(time.time())),
        "Content-Type": "application/json"})


def test_predicate():
    assert spine.should_auto_enroll(True, False) is True
    assert spine.should_auto_enroll(True, None) is True
    assert spine.should_auto_enroll(True, True) is False   # never downgrade / touch
    assert spine.should_auto_enroll(False, False) is False # flag off


def _wire(monkeypatch, monitoring_enabled):
    calls, tl = [], []
    async def get_site(sid):
        return {"id": sid, "url": "https://acme.co", "monitoring_enabled": monitoring_enabled}
    async def set_mon(sid, enabled, freq=None):
        calls.append((sid, enabled, freq))
    async def tladd(rs, rd, t, p, source="spine"):
        tl.append(t)
    async def slack(t):
        return None
    monkeypatch.setattr(database, "get_site", get_site)
    monkeypatch.setattr(database, "set_monitoring", set_mon)
    monkeypatch.setattr(database, "timeline_add", tladd)
    monkeypatch.setattr(spine, "_slack", slack)
    return calls, tl


def test_enroll_when_flag_on_and_unmonitored(monkeypatch):
    monkeypatch.setenv("AUTO_ENROLL", "1")
    calls, tl = _wire(monkeypatch, monitoring_enabled=False)
    assert _post(COMPLETED).status_code == 200
    assert calls == [("s1", True, "Weekly")]            # off → weekly
    assert "monitoring.auto_enrolled" in tl


def test_never_touch_a_monitored_site(monkeypatch):
    monkeypatch.setenv("AUTO_ENROLL", "1")
    calls, tl = _wire(monkeypatch, monitoring_enabled=True)  # e.g. an existing daily cadence
    assert _post(COMPLETED).status_code == 200
    assert calls == []                                   # never downgrade / re-enroll
    assert "monitoring.auto_enrolled" not in tl


def test_idempotent_second_event_after_enroll(monkeypatch):
    # once enrolled, the site reads monitored → a repeat event is a no-op
    monkeypatch.setenv("AUTO_ENROLL", "1")
    calls, tl = _wire(monkeypatch, monitoring_enabled=True)
    assert _post(COMPLETED).status_code == 200
    assert calls == []


def test_flag_off_byte_identical(monkeypatch):
    # AUTO_ENROLL unset → set_monitoring never called
    calls, tl = _wire(monkeypatch, monitoring_enabled=False)
    assert _post(COMPLETED).status_code == 200
    assert calls == []
