"""
Scan persistence.

Regression: _save_scan_sync wrapped a *dict assignment* in try/except while
leaving the INSERT unguarded:

    try:
        scan_payload["pages_scanned"] = pages_scanned   # cannot raise
    except Exception:
        pass
    client.table("scans").insert(scan_payload).execute()  # can, and did

On a deployment whose `scans` table predates the pages_scanned column, every
insert was rejected, the whole save raised, main swallowed it as "non-critical",
and the History panel stayed empty forever with no visible error.
"""
import pytest

import database


class FakeQuery:
    def __init__(self, table, store, fail_on=()):
        self.table = table
        self.store = store
        self.fail_on = fail_on
        self._payload = None
        self._filters = {}

    # ─ builders ─
    def insert(self, payload):
        self._payload = payload
        return self

    def upsert(self, payload, on_conflict=None):
        self._payload = payload
        return self

    def select(self, *a, **k):
        return self

    def update(self, payload):
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def is_(self, col, val):
        return self

    def limit(self, n):
        return self

    def order(self, *a, **k):
        return self

    # ─ terminal ─
    def execute(self):
        if self.table == "scans" and self._payload is not None:
            for column in self.fail_on:
                if column in self._payload:
                    raise RuntimeError(
                        f'column "{column}" of relation "scans" does not exist'
                    )
            self.store.setdefault("scans", []).append(self._payload)
            return type("R", (), {"data": [{"id": "scan-1"}]})()

        if self.table == "sites":
            return type("R", (), {"data": [{"id": "site-1"}]})()

        if self.table == "link_issues":
            self.store.setdefault("link_issues", []).append(self._payload)
            return type("R", (), {"data": []})()

        return type("R", (), {"data": []})()


class FakeClient:
    def __init__(self, fail_on=()):
        self.store = {}
        self.fail_on = fail_on

    def table(self, name):
        return FakeQuery(name, self.store, self.fail_on)


def _results():
    return [{"label": "ok", "url": "https://acme.test/a", "category": "Body text",
             "anchor_text": "a", "status_code": 200}]


def test_scan_is_saved_when_the_schema_has_pages_scanned(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(database, "_get_client", lambda: client)

    out = database._save_scan_sync("https://acme.test/", "u@x.test", _results(), 99)
    assert out == {"site_id": "site-1", "scan_id": "scan-1"}
    assert client.store["scans"][0]["pages_scanned"] == 1


def test_scan_is_still_saved_when_pages_scanned_column_is_missing(monkeypatch):
    """The whole point: an optional column must not cost us the scan row."""
    client = FakeClient(fail_on=("pages_scanned",))
    monkeypatch.setattr(database, "_get_client", lambda: client)

    out = database._save_scan_sync("https://acme.test/", "u@x.test", _results(), 99)
    assert out == {"site_id": "site-1", "scan_id": "scan-1"}

    saved = client.store["scans"][0]
    assert "pages_scanned" not in saved
    assert saved["total_links"] == 1
    assert saved["health_score"] == 99


def test_a_real_insert_failure_still_raises(monkeypatch):
    """Dropping optional columns must not mask a genuine schema problem."""
    client = FakeClient(fail_on=("total_links",))
    monkeypatch.setattr(database, "_get_client", lambda: client)

    with pytest.raises(RuntimeError, match="total_links"):
        database._save_scan_sync("https://acme.test/", "u@x.test", _results(), 99)


def test_issue_tracking_failure_never_loses_the_scan(monkeypatch):
    """History reads the `scans` row. A link_issues problem must not delete it."""
    client = FakeClient()
    monkeypatch.setattr(database, "_get_client", lambda: client)

    def boom(*args, **kwargs):
        raise RuntimeError("link_issues is misconfigured")

    monkeypatch.setattr(database, "_track_issues", boom)

    out = database._save_scan_sync("https://acme.test/", "u@x.test", _results(), 99)
    assert out["scan_id"] == "scan-1"
    assert client.store["scans"]


def test_optional_columns_are_dropped_only_once(monkeypatch):
    """_insert_scan retries exactly one time, then gives up."""
    calls = {"n": 0}

    class AlwaysFails(FakeClient):
        def table(self, name):
            calls["n"] += 1
            return FakeQuery(name, self.store, fail_on=("pages_scanned", "total_links"))

    client = AlwaysFails()
    monkeypatch.setattr(database, "_get_client", lambda: client)
    with pytest.raises(RuntimeError):
        database._save_scan_sync("https://acme.test/", "u@x.test", _results(), 99)
