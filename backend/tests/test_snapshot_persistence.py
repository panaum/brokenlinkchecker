"""
Snapshot persistence.

Three scans of a site produced 0 rows in scan_snapshots. The write was failing
and the error was being reduced to `str(e)`, which on a PostgREST APIError drops
the code / details / hint — exactly where "row-level security policy" and
"column ... does not exist" live.

These tests pin the persistence path: the payload is whitelisted, a batch
failure degrades to per-row inserts that name the offending row, a snapshot skip
is never silent, and a failed write never takes the scan down.
"""
import pytest

import database
from database import FINDING_COLUMNS, _finding_row, describe_exception


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, name, db):
        self.name = name
        self.db = db
        self._payload = None
        self._op = None

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def select(self, *a, **k):
        self._op = "select"
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, *a):
        return self

    def is_(self, *a):
        return self

    def limit(self, *a):
        return self

    def order(self, *a, **k):
        return self

    def execute(self):
        db = self.db
        if self._op == "insert":
            fail = db.fail.get(self.name)
            if fail:
                rows = self._payload if isinstance(self._payload, list) else [self._payload]
                if any(fail(row) for row in rows):
                    raise db.error_factory()
            payload = self._payload
            rows = payload if isinstance(payload, list) else [payload]
            db.rows.setdefault(self.name, []).extend(rows)
            return FakeResult([{"id": f"{self.name}-1"}])
        if self._op == "select" and self.name == "sites":
            return FakeResult([{"id": "site-1"}])
        return FakeResult([])


class FakeDB:
    def __init__(self, fail=None, error_factory=None):
        self.rows = {}
        self.fail = fail or {}
        self.error_factory = error_factory or (lambda: RuntimeError("boom"))

    def table(self, name):
        return FakeTable(name, self)


class PostgrestLikeError(Exception):
    """Mimics postgrest.APIError: str() is terse, the useful body is in attrs."""

    def __init__(self):
        super().__init__("Bad Request")
        self.message = "new row violates row-level security policy"
        self.code = "42501"
        self.details = 'for table "scan_snapshots"'
        self.hint = "enable an insert policy or use the service role key"

    def __str__(self):
        return "Bad Request"


@pytest.fixture(autouse=True)
def _reset_error():
    database._last_snapshot_error = None
    yield
    database._last_snapshot_error = None


# ─── whitelist ───────────────────────────────────────────────────────────────
def test_finding_row_keeps_only_real_columns():
    """PostgREST rejects the ENTIRE batch if one row carries an unknown key."""
    row = _finding_row(
        {"fingerprint": "abc", "bucket": "broken", "url": "https://x.test/",
         "age_days": 5, "diff_status": "new", "fingerprint_extra": 1},
        "snap-1", "site-1",
    )
    assert set(row) - {"snapshot_id", "site_id"} <= FINDING_COLUMNS
    assert "age_days" not in row and "diff_status" not in row
    assert row["snapshot_id"] == "snap-1" and row["site_id"] == "site-1"


def test_finding_row_survives_a_model_gaining_a_field():
    row = _finding_row({"fingerprint": "a", "bucket": "broken", "url": "u",
                        "some_future_field": object()}, "s", "site")
    assert "some_future_field" not in row


# ─── describe_exception ──────────────────────────────────────────────────────
def test_describe_exception_recovers_the_postgrest_body():
    info = describe_exception(PostgrestLikeError())
    assert info["str"] == "Bad Request"                 # what we used to log
    assert "row-level security" in info["message"]      # what we needed
    assert info["code"] == "42501"
    assert info["hint"]


def test_describe_exception_on_a_plain_error():
    info = describe_exception(ValueError("nope"))
    assert info["type"] == "ValueError" and info["args"] == ["nope"]


# ─── snapshot insert ─────────────────────────────────────────────────────────
def _findings(n=2):
    return [{"fingerprint": f"fp{i}", "bucket": "broken", "confidence": "high",
             "url": f"https://x.test/{i}", "anchor_text": "a", "zone": "CTA",
             "reason": "r", "first_seen_at": "2026-07-10T00:00:00+00:00",
             "resolved_at": None, "status": "open"} for i in range(n)]


def test_snapshot_and_findings_are_written(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(database, "_get_client", lambda: db)

    snapshot_id = database._save_snapshot_sync(
        "site-1", "scan-1", {"link_fingerprints": ["a", "b"]}, _findings(2), [])

    assert snapshot_id == "scan_snapshots-1"
    assert len(db.rows["scan_snapshots"]) == 1
    assert len(db.rows["findings"]) == 2
    assert database.last_snapshot_error() is None


def test_snapshot_insert_failure_records_the_full_error_and_raises(monkeypatch):
    db = FakeDB(fail={"scan_snapshots": lambda row: True},
                error_factory=PostgrestLikeError)
    monkeypatch.setattr(database, "_get_client", lambda: db)

    with pytest.raises(PostgrestLikeError):
        database._save_snapshot_sync("site-1", "scan-1", {}, _findings(1), [])

    err = database.last_snapshot_error()
    assert err["stage"] == "scan_snapshots.insert"
    assert "row-level security" in err["message"]
    assert err["site_id"] == "site-1"


def test_findings_batch_failure_falls_back_to_row_by_row(monkeypatch):
    """One bad row must not discard every finding in the scan."""
    def fail_batch(row):
        return row["fingerprint"] == "fp1"

    db = FakeDB(fail={"findings": fail_batch})
    monkeypatch.setattr(database, "_get_client", lambda: db)

    snapshot_id = database._save_snapshot_sync(
        "site-1", "scan-1", {}, _findings(3), [])

    assert snapshot_id                                    # snapshot survived
    written = [r["fingerprint"] for r in db.rows["findings"]]
    assert written == ["fp0", "fp2"]                      # fp1 is the bad row

    err = database.last_snapshot_error()
    assert err["stage"] == "findings.insert(row)"
    assert err["fingerprint"] == "fp1"


def test_findings_failure_never_discards_the_snapshot(monkeypatch):
    db = FakeDB(fail={"findings": lambda row: True})
    monkeypatch.setattr(database, "_get_client", lambda: db)

    snapshot_id = database._save_snapshot_sync("site-1", "scan-1", {}, _findings(2), [])
    assert snapshot_id
    assert len(db.rows["scan_snapshots"]) == 1


def test_a_site_with_no_findings_still_gets_a_snapshot(monkeypatch):
    """0 broken links is a legitimate result. The snapshot is the baseline."""
    db = FakeDB()
    monkeypatch.setattr(database, "_get_client", lambda: db)

    assert database._save_snapshot_sync("site-1", "scan-1", {}, [], [])
    assert len(db.rows["scan_snapshots"]) == 1
    assert "findings" not in db.rows


def test_a_clean_write_clears_the_previous_error(monkeypatch):
    database._last_snapshot_error = {"stage": "stale"}
    db = FakeDB()
    monkeypatch.setattr(database, "_get_client", lambda: db)

    database._save_snapshot_sync("site-1", "scan-1", {}, _findings(1), [])
    assert database.last_snapshot_error() is None


# ─── write probe ─────────────────────────────────────────────────────────────
def test_write_probe_reports_the_insert_error_and_cleans_up(monkeypatch):
    db = FakeDB(fail={"scan_snapshots": lambda row: True},
                error_factory=PostgrestLikeError)
    monkeypatch.setattr(database, "_get_client", lambda: db)

    out = database._snapshot_write_probe_sync("https://x.test/", "u@x.test")
    assert out["ok"] is False
    assert out["stage"] == "scan_snapshots.insert"
    assert "row-level security" in out["error"]["message"]


def test_write_probe_succeeds_and_removes_its_rows(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(database, "_get_client", lambda: db)

    out = database._snapshot_write_probe_sync("https://x.test/", "u@x.test")
    assert out["ok"] is True
    assert out["cleaned_up"] is True


def test_write_probe_reports_a_missing_site(monkeypatch):
    class NoSite(FakeDB):
        def table(self, name):
            t = FakeTable(name, self)
            if name == "sites":
                t.execute = lambda: FakeResult([])
            return t

    monkeypatch.setattr(database, "_get_client", lambda: NoSite())
    out = database._snapshot_write_probe_sync("https://x.test/", "u@x.test")
    assert out["ok"] is False and out["stage"] == "sites.select"
