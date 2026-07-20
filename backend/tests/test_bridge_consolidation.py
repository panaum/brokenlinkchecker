"""Fix 4 — bridge consolidation (qa_bridge_map ↔ registry deliverables).

The load-bearing guarantee is the SNAPSHOT test: with QA_BRIDGE_CONSOLIDATION
off, qa_resolve_map() must return exactly what qa_get_map() returns for every
input, and must not consult the registry at all. Everything else is the
flag-on behaviour.

See docs/design-notes/fix4-bridge-consolidation.md.
"""
import asyncio
import inspect

import database


def _run(coro):
    return asyncio.run(coro)


LEGACY_ROW = {
    "id": "map-1",
    "qa_page_ref": "page-abc",
    "linkspy_site_id": "site-legacy",
    "page_url": "https://example.com/legacy",
    "created_by": "op@apexure.com",
    "created_at": "2026-01-01T00:00:00+00:00",
}

DELIVERABLE_ROW = {
    "id": "dlv-1",
    "site_id": "site-registry",
    "kind": "page",
    "name": "Instructor Individual",
    "external_ref": "page-abc",
    "url": "https://example.com/registry",
    "created_at": "2026-02-02T00:00:00+00:00",
    "archived_at": None,
}


class _Spy:
    """Records whether the registry was consulted."""

    def __init__(self, deliverable):
        self.deliverable = deliverable
        self.calls = 0

    async def __call__(self, ref):
        self.calls += 1
        return self.deliverable


def _patch(monkeypatch, legacy, deliverable, flag):
    async def fake_get_map(ref):
        return legacy

    spy = _Spy(deliverable)
    monkeypatch.setattr(database, "qa_get_map", fake_get_map)
    monkeypatch.setattr(database, "registry_get_deliverable", spy)
    if flag is None:
        monkeypatch.delenv("QA_BRIDGE_CONSOLIDATION", raising=False)
    else:
        monkeypatch.setenv("QA_BRIDGE_CONSOLIDATION", flag)
    return spy


# ══ SNAPSHOT: flag OFF is byte-identical to today ═══════════════════════════
def test_flag_off_returns_exactly_the_legacy_row(monkeypatch):
    _patch(monkeypatch, LEGACY_ROW, DELIVERABLE_ROW, flag=None)
    got = _run(database.qa_resolve_map("page-abc"))
    assert got == LEGACY_ROW
    assert got is LEGACY_ROW          # same object — no copying, no adaptation


def test_flag_off_never_consults_the_registry_even_when_unmapped(monkeypatch):
    """The critical one: a ref with NO legacy row but a perfectly good registry
    deliverable must still resolve to None while the flag is off."""
    spy = _patch(monkeypatch, None, DELIVERABLE_ROW, flag=None)
    assert _run(database.qa_resolve_map("page-abc")) is None
    assert spy.calls == 0             # registry not touched at all


def test_flag_off_snapshot_matrix_matches_qa_get_map(monkeypatch):
    """For every input shape, flag-off resolution == the legacy lookup."""
    for legacy in (LEGACY_ROW, None):
        for deliverable in (DELIVERABLE_ROW, None, {"__registry__": "not_provisioned"}):
            spy = _patch(monkeypatch, legacy, deliverable, flag=None)
            assert _run(database.qa_resolve_map("page-abc")) == legacy
            assert spy.calls == 0


def test_non_literal_one_values_are_treated_as_off(monkeypatch):
    """Strict == "1", matching JOBS_SHADOW / FLYWHEEL / SPINE_CONSUME."""
    for value in ("true", "True", "on", "yes", "0", "", " 1"):
        spy = _patch(monkeypatch, None, DELIVERABLE_ROW, flag=value)
        assert _run(database.qa_resolve_map("page-abc")) is None, value
        assert spy.calls == 0, value


# ══ Flag ON ═════════════════════════════════════════════════════════════════
def test_flag_on_legacy_map_still_wins(monkeypatch):
    """An explicit manual mapping is an operator override — it must keep
    winning, and the registry must not even be consulted."""
    spy = _patch(monkeypatch, LEGACY_ROW, DELIVERABLE_ROW, flag="1")
    got = _run(database.qa_resolve_map("page-abc"))
    assert got is LEGACY_ROW
    assert got["linkspy_site_id"] == "site-legacy"   # not site-registry
    assert spy.calls == 0


def test_flag_on_falls_back_to_registry_when_unmapped(monkeypatch):
    spy = _patch(monkeypatch, None, DELIVERABLE_ROW, flag="1")
    got = _run(database.qa_resolve_map("page-abc"))
    assert spy.calls == 1
    assert got["linkspy_site_id"] == "site-registry"
    assert got["page_url"] == "https://example.com/registry"
    assert got["created_at"] == "2026-02-02T00:00:00+00:00"
    assert got["qa_page_ref"] == "page-abc"
    assert got["__source__"] == "registry"


def test_flag_on_with_neither_source_is_none(monkeypatch):
    _patch(monkeypatch, None, None, flag="1")
    assert _run(database.qa_resolve_map("page-abc")) is None


def test_adapted_row_carries_everything_qa_snapshot_needs(monkeypatch):
    """qa_snapshot(site_id, page_url, baseline_at) — all three must be present
    and non-placeholder, or the fallback is useless."""
    _patch(monkeypatch, None, DELIVERABLE_ROW, flag="1")
    got = _run(database.qa_resolve_map("page-abc"))
    assert got["linkspy_site_id"] and got["created_at"]
    assert "page_url" in got          # nullable, but the key must exist


# ══ The adapter in isolation ════════════════════════════════════════════════
def test_deliverable_as_map_rejects_sentinels_and_junk():
    assert database.deliverable_as_map(None) is None
    assert database.deliverable_as_map({}) is None
    assert database.deliverable_as_map({"__registry__": "not_provisioned"}) is None
    assert database.deliverable_as_map({"__registry__": "conflict"}) is None
    # a deliverable with no site_id has nothing to snapshot
    assert database.deliverable_as_map({"external_ref": "p", "site_id": None}) is None


def test_deliverable_as_map_maps_nullable_url_to_none():
    row = dict(DELIVERABLE_ROW, url=None)
    assert database.deliverable_as_map(row)["page_url"] is None


# ══ Constitution guards ═════════════════════════════════════════════════════
def test_resolver_is_read_only():
    """The consolidation must never write, upsert or delete anything."""
    src = inspect.getsource(database.qa_resolve_map) + inspect.getsource(database.deliverable_as_map)
    for forbidden in ("insert", "upsert", "update", "delete", "qa_add_map", "qa_unlink"):
        assert forbidden not in src, f"qa_resolve_map must not {forbidden}"


def test_legacy_writers_and_readers_still_exist():
    """qa_bridge_map is deprecated as the SOLE source, not removed. The admin
    UI's read/write paths must survive this change."""
    for name in ("qa_add_map", "qa_get_map", "qa_list_maps", "qa_unlink"):
        assert callable(getattr(database, name)), f"{name} was removed"
