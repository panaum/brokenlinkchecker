"""Phase 5 Part A wiring — resolution hook, outbox drain, absorption, integration.
FLYWHEEL default off must be byte-identical (no side effects). Sync tests drive
the async code via asyncio.run (no pytest-asyncio dependency)."""
import asyncio

import pytest

import database
import flywheel
import spine
from spine_contract import EVENT_TYPES


def run(coro):
    return asyncio.run(coro)


class _Rec:
    """Records async calls; returns a configurable value."""
    def __init__(self, ret=None):
        self.calls = []
        self.ret = ret

    async def __call__(self, *a, **k):
        self.calls.append((a, k))
        return self.ret


@pytest.fixture
def wired(monkeypatch):
    cand = _Rec(ret={"id": "cand-1"})
    outbox = _Rec(ret={"id": "evt-1"})
    tl = _Rec()
    setstat = _Rec()
    monkeypatch.setattr(database, "candidate_create", cand)
    monkeypatch.setattr(database, "spine_outbox_add", outbox)
    monkeypatch.setattr(database, "timeline_add", tl)
    monkeypatch.setattr(database, "candidate_set_status", setstat)

    async def no_prefills(_id):
        return []
    monkeypatch.setattr(database, "prefills_latest", no_prefills)
    return {"cand": cand, "outbox": outbox, "tl": tl, "setstat": setstat}


# ── A2: FLYWHEEL-off regression (byte-identical: zero side effects) ──
def test_flywheel_off_is_a_noop(monkeypatch, wired):
    monkeypatch.delenv("FLYWHEEL", raising=False)
    res = run(flywheel.on_incident_resolved("inc-1", "sentinel_indexability"))
    assert res == {"skipped": True}
    assert wired["cand"].calls == [] and wired["outbox"].calls == [] and wired["tl"].calls == []


# ── A2: uncovered class → candidate + outbox event ──
def test_uncovered_drafts_candidate_and_emits(monkeypatch, wired):
    monkeypatch.setenv("FLYWHEEL", "1")
    res = run(flywheel.on_incident_resolved("inc-2", "sentinel_indexability"))
    assert res["verdict"] == "uncovered" and res["candidate_drafted"] is True
    assert len(wired["cand"].calls) == 1
    args, _ = wired["outbox"].calls[0]
    assert args[0] == EVENT_TYPES["CANDIDATE_CREATED"]
    assert args[1]["candidate_id"] == "cand-1" and args[1]["proposed_check_key"] == "indexability_ok"


# ── A2: covered class → timeline note only, no candidate ──
def test_covered_writes_timeline_note_no_candidate(monkeypatch, wired):
    monkeypatch.setenv("FLYWHEEL", "1")
    res = run(flywheel.on_incident_resolved("inc-3", "finding_broken"))
    assert res["verdict"] == "process" and wired["cand"].calls == []
    assert wired["tl"].calls[0][0][2] == "flywheel.gap_process"


def test_covered_passed_at_delivery_is_drift(monkeypatch, wired):
    monkeypatch.setenv("FLYWHEEL", "1")
    async def holding(_id):
        return [{"check_key": "uptime", "verdict": "holding"}]
    monkeypatch.setattr(database, "prefills_latest", holding)
    res = run(flywheel.on_incident_resolved("inc-4", "sentinel_uptime", deliverable_id="d1"))
    assert res["verdict"] == "drift"
    assert wired["tl"].calls[0][0][2] == "flywheel.gap_drift"


# ── A3: outbox drain marks delivered on 2xx / failed on non-2xx ──
class _Resp:
    def __init__(self, code):
        self.status_code = code


class _FakeClient:
    def __init__(self, code):
        self._code = code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        return _Resp(self._code)


def test_drain_marks_delivered_on_2xx(monkeypatch):
    monkeypatch.setenv("QA_APP_URL", "https://qa.example.com")
    monkeypatch.setenv("SPINE_SECRET", "s3cr3t")

    async def undelivered(limit=20):
        return [{"id": "row-1", "type": EVENT_TYPES["CANDIDATE_CREATED"],
                 "created_at": "2026-07-16T00:00:00Z", "payload": {"candidate_id": "cand-1"}}]
    delivered, setstat = _Rec(), _Rec()
    monkeypatch.setattr(database, "spine_outbox_undelivered", undelivered)
    monkeypatch.setattr(database, "spine_outbox_mark_delivered", delivered)
    monkeypatch.setattr(database, "spine_outbox_mark_failed", _Rec())
    monkeypatch.setattr(database, "candidate_set_status", setstat)
    monkeypatch.setattr(spine.httpx, "AsyncClient", lambda *a, **k: _FakeClient(200))
    out = run(spine.spine_outbox_drain())
    assert out == {"delivered": 1, "failed": 0}
    assert len(delivered.calls) == 1
    assert setstat.calls[0][0] == ("cand-1", "sent", "sent_at")


def test_drain_marks_failed_and_keeps_row_on_non_2xx(monkeypatch):
    monkeypatch.setenv("QA_APP_URL", "https://qa.example.com")
    monkeypatch.setenv("SPINE_SECRET", "s3cr3t")

    async def undelivered(limit=20):
        return [{"id": "row-2", "type": EVENT_TYPES["CANDIDATE_CREATED"], "created_at": "x", "payload": {}}]
    failed, delivered = _Rec(), _Rec()
    monkeypatch.setattr(database, "spine_outbox_undelivered", undelivered)
    monkeypatch.setattr(database, "spine_outbox_mark_delivered", delivered)
    monkeypatch.setattr(database, "spine_outbox_mark_failed", failed)
    monkeypatch.setattr(spine.httpx, "AsyncClient", lambda *a, **k: _FakeClient(500))
    out = run(spine.spine_outbox_drain())
    assert out == {"delivered": 0, "failed": 1}
    assert len(failed.calls) == 1 and delivered.calls == []


# ── integration: uncovered incident → candidate → outbox → drain delivers ──
def test_integration_linkspy_half(monkeypatch, wired):
    monkeypatch.setenv("FLYWHEEL", "1")
    monkeypatch.setenv("QA_APP_URL", "https://qa.example.com")
    monkeypatch.setenv("SPINE_SECRET", "s3cr3t")
    run(flywheel.on_incident_resolved("inc-int", "ads_dead_destination"))
    assert wired["outbox"].calls, "outbox event emitted"
    evt = wired["outbox"].calls[0][0][1]

    async def undelivered(limit=20):
        return [{"id": "row-int", "type": EVENT_TYPES["CANDIDATE_CREATED"], "created_at": "x", "payload": evt}]
    monkeypatch.setattr(database, "spine_outbox_undelivered", undelivered)
    monkeypatch.setattr(database, "spine_outbox_mark_delivered", _Rec())
    monkeypatch.setattr(database, "spine_outbox_mark_failed", _Rec())
    monkeypatch.setattr(spine.httpx, "AsyncClient", lambda *a, **k: _FakeClient(200))
    out = run(spine.spine_outbox_drain())
    assert out["delivered"] == 1
    # absorption of a mocked item_promoted (machine_verifiable, no battery key yet)
    assert flywheel.absorption_outcome(evt["proposed_check_key"], True) == "promoted_unimplemented"
