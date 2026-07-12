"""Persistence-layer guards for the vigilance report:
 - the duplicate-fire guard (monthly generation must not create duplicate rows)
 - the print stylesheet's page-break integrity rules (client-ready PDF)
"""
import pathlib
import types

import database


class _FakeTable:
    def __init__(self, recorder):
        self.recorder = recorder

    def upsert(self, row, on_conflict=None):
        self.recorder.append({"row": row, "on_conflict": on_conflict})
        return self

    def execute(self):
        last = self.recorder[-1]["row"]
        return types.SimpleNamespace(data=[{"id": "r1", **last}])


class _FakeClient:
    def __init__(self, recorder):
        self.recorder = recorder

    def table(self, _name):
        return _FakeTable(self.recorder)


def test_duplicate_fire_guard_upserts_on_period(monkeypatch):
    """Generating twice for the same (site, period) must upsert on the unique key,
    never blind-insert — so a re-fired monthly job replaces, not duplicates."""
    rec = []
    monkeypatch.setattr(database, "_get_client", lambda: _FakeClient(rec))
    database._save_report_sync("site-1", "s", "e", "June 2026", {"score": 100})
    database._save_report_sync("site-1", "s", "e", "June 2026", {"score": 90})
    assert len(rec) == 2
    assert all(c["on_conflict"] == "site_id,period_label" for c in rec)
    assert all(c["row"]["period_label"] == "June 2026" for c in rec)


def test_print_stylesheet_guards_page_breaks():
    """The print rules that keep incident cards whole and force backgrounds must
    stay present — a client-ready PDF depends on them."""
    css = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "app" / "globals.css"
    text = css.read_text(encoding="utf-8")
    assert "@media print" in text
    assert "break-inside: avoid" in text          # incident cards + sections never split
    assert "print-color-adjust: exact" in text    # light palette + backgrounds actually print
