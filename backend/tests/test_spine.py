"""Phase 2C — spine inbox: HMAC/skew, idempotency (dup → no double enqueue),
SPINE_CONSUME gating, heartbeat. DB + enqueue monkeypatched (no live services)."""
import json
import time

import pytest
from fastapi.testclient import TestClient

import main
import database
import jobs
from spine_contract import (sign, verify, SPINE_SIG_HEADER, SPINE_SENT_AT_HEADER,
                            SKEW_MAX_SECONDS, EVENT_TYPES, CONTRACT_CHECKSUM)

client = TestClient(main.app)
SECRET = "test-secret"


@pytest.fixture(autouse=True)
def _spine_env(monkeypatch):
    monkeypatch.setenv("SPINE_SECRET", SECRET)
    monkeypatch.delenv("SPINE_CONSUME", raising=False)

    async def ins(event_id, type_, payload):
        return {"duplicate": False}
    async def noop(*a, **k):
        return None
    monkeypatch.setattr(database, "spine_inbox_insert", ins)
    monkeypatch.setattr(database, "spine_inbox_mark", noop)
    monkeypatch.setattr(database, "timeline_add", noop)
    monkeypatch.setattr(database, "spine_marker_set", noop)


def _post(envelope, secret=SECRET, sent=None):
    raw = json.dumps(envelope)
    sent = sent if sent is not None else str(int(time.time()))
    return client.post("/api/spine/inbox", content=raw, headers={
        SPINE_SIG_HEADER: sign(raw, secret), SPINE_SENT_AT_HEADER: sent,
        "Content-Type": "application/json"})


READY = {"id": "e1", "type": EVENT_TYPES["READY_FOR_QA"], "schema_version": 1,
         "occurred_at": "2026-07-16T00:00:00Z", "producer": "qa",
         "registry_deliverable_id": "d1", "registry_site_id": "s1",
         "payload": {"qa_page_ref": "p1", "url": "https://acme.co/lp", "name": "LP"}}


# ── pure HMAC parity/rejects (python side) ──
def test_contract_checksum_and_hmac():
    assert CONTRACT_CHECKSUM.startswith("175499b1")
    now = 1_000_000
    assert verify("body", SECRET, sign("body", SECRET), str(now), now)[0] is True
    assert verify("body", SECRET, sign("body", "other"), str(now), now)[0] is False
    assert verify("body", SECRET, sign("body", SECRET), str(now - SKEW_MAX_SECONDS - 5), now)[0] is False


# ── endpoint auth ──
def test_bad_signature_401():
    r = _post(READY, secret="wrong-secret")
    assert r.status_code == 401


def test_skew_401():
    r = _post(READY, sent=str(int(time.time()) - (SKEW_MAX_SECONDS + 60)))
    assert r.status_code == 401


# ── idempotency: duplicate event id → 200 duplicate, no enqueue ──
def test_duplicate_no_double_enqueue(monkeypatch):
    async def dup(*a, **k):
        return {"duplicate": True}
    monkeypatch.setattr(database, "spine_inbox_insert", dup)
    calls = []
    async def fake_enqueue(kind, payload=None, **k):
        calls.append(kind)
    monkeypatch.setattr(jobs, "enqueue", fake_enqueue)
    r = _post(READY)
    assert r.status_code == 200 and r.json().get("duplicate") is True
    assert calls == []  # never enqueued on a duplicate


# ── SPINE_CONSUME gating ──
def test_ready_consume_off_records_not_enqueues(monkeypatch):
    calls = []
    async def fake_enqueue(kind, payload=None, **k):
        calls.append(kind)
    monkeypatch.setattr(jobs, "enqueue", fake_enqueue)
    r = _post(READY)
    assert r.status_code == 200 and r.json().get("enqueued") is False
    assert calls == []  # shadow: recorded, not consumed


def test_ready_consume_on_enqueues_once(monkeypatch):
    monkeypatch.setenv("SPINE_CONSUME", "1")
    calls = []
    async def fake_enqueue(kind, payload=None, *, idempotency_key=None, **k):
        calls.append((kind, idempotency_key))
    monkeypatch.setattr(jobs, "enqueue", fake_enqueue)
    r = _post(READY)
    assert r.status_code == 200 and r.json().get("enqueued") is True
    assert calls == [("qa_battery", "e1")]  # single enqueue, idempotency = event id


# ── heartbeat updates the marker, never enqueues ──
def test_heartbeat_marks_never_enqueues(monkeypatch):
    marks = []
    async def mk(key):
        marks.append(key)
    monkeypatch.setattr(database, "spine_marker_set", mk)
    calls = []
    async def fake_enqueue(kind, payload=None, **k):
        calls.append(kind)
    monkeypatch.setattr(jobs, "enqueue", fake_enqueue)
    hb = {"id": "h1", "type": EVENT_TYPES["HEARTBEAT"], "schema_version": 1,
          "occurred_at": "2026-07-16T00:00:00Z", "producer": "qa", "payload": {}}
    r = _post(hb)
    assert r.status_code == 200 and r.json().get("heartbeat") is True
    assert "heartbeat" in marks and calls == []
