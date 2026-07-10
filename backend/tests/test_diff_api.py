"""
End-to-end diffing through the real /scan endpoint and the diff endpoint,
against an in-memory stand-in for Supabase.

Acceptance #4: two scans of one site produce correct new / fixed / recurring,
and the first scan reports no baseline (the UI renders n/a) rather than
claiming every pre-existing issue is new.
"""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import main
from models import RawLink


PAGE = "https://acme.test/"


def _raw(**over) -> RawLink:
    fields = dict(
        url="https://acme.test/a", source_element="a", anchor_text="A",
        category="Body text", is_external=False,
    )
    fields.update(over)
    return RawLink(**fields)


# Scan 1: A works, B is 404, C is a dead CTA.
SCAN_1 = [
    _raw(url="https://acme.test/a", anchor_text="A"),
    _raw(url="https://acme.test/b", anchor_text="B"),
    _raw(url=PAGE, anchor_text="Buy Now", category="Dead CTA", bucket="dead_cta",
         confidence="high", link_kind="dead_cta", reason="Anchor href goes nowhere"),
]
# Scan 2: B removed entirely (fixed), D is a new 404, C still dead.
SCAN_2 = [
    _raw(url="https://acme.test/a", anchor_text="A"),
    _raw(url="https://acme.test/d", anchor_text="D"),
    _raw(url=PAGE, anchor_text="Buy Now", category="Dead CTA", bucket="dead_cta",
         confidence="high", link_kind="dead_cta", reason="Anchor href goes nowhere"),
]

_STATUS = {"/a": 200, "/b": 404, "/d": 404, "/": 200}


class FakeDB:
    """Minimal stand-in for the scan_snapshots + findings tables."""

    def __init__(self):
        self.snapshots = []       # newest last
        self.findings = {}        # snapshot_id -> [row dicts]
        self._n = 0

    async def get_site_id(self, site_url, user_email):
        return "site-1"

    async def get_latest_snapshot(self, site_id):
        return self.snapshots[-1] if self.snapshots else None

    async def get_recent_snapshots(self, site_id, limit=2):
        return list(reversed(self.snapshots))[:limit]

    async def get_findings_for_snapshot(self, snapshot_id):
        return list(self.findings.get(snapshot_id, []))

    async def save_scan(self, **kwargs):
        self._n += 1
        return {"site_id": "site-1", "scan_id": f"scan-{self._n}"}

    async def save_snapshot(self, site_id, scan_id, totals, findings, resolved):
        snapshot_id = f"snap-{len(self.snapshots) + 1}"
        self.snapshots.append({
            "id": snapshot_id,
            "created_at": f"2026-07-{10 + len(self.snapshots):02d}T00:00:00+00:00",
            "totals_json": totals,
        })
        self.findings[snapshot_id] = [dict(f) for f in findings]

        # Stamp resolved findings on whichever earlier snapshot holds them.
        resolved_map = dict(resolved)
        for rows in self.findings.values():
            for row in rows:
                if row["fingerprint"] in resolved_map and not row.get("resolved_at"):
                    row["resolved_at"] = resolved_map[row["fingerprint"]]
                    row["status"] = "resolved"
        return snapshot_id


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    for name in ("get_site_id", "get_latest_snapshot", "get_recent_snapshots",
                 "get_findings_for_snapshot", "save_scan", "save_snapshot"):
        monkeypatch.setattr(main, name, getattr(fake, name))

    async def fake_suggestions(results):
        return results

    async def fake_slack(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "process_suggestions", fake_suggestions)
    monkeypatch.setattr(main, "send_slack_notification", fake_slack)
    return fake


def _install_scrape(monkeypatch, links):
    async def fake_scrape(url):
        return list(links), ["Astro"], {}

    async def fake_check_all(links_):
        from checker import check_single

        def handler(request):
            return httpx.Response(_STATUS.get(request.url.path, 200))

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as c:
            for i, link in enumerate(links_, start=1):
                yield i, await check_single(c, link)

    monkeypatch.setattr(main, "scrape_links", fake_scrape)
    monkeypatch.setattr(main, "check_all_links", fake_check_all)


def _scan(client) -> dict:
    with client.stream("GET", "/scan", params={"url": PAGE, "email": "u@x.test"}) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[len("data: "):])
                if payload.get("type") == "result":
                    return payload
    raise AssertionError("no result event")


# ─── first scan: no baseline ────────────────────────────────────────────────
def test_first_scan_reports_no_baseline(db, monkeypatch):
    _install_scrape(monkeypatch, SCAN_1)
    diff = _scan(TestClient(main.app))["diff"]

    assert diff["has_baseline"] is False
    assert diff["summary"] == "First scan — no baseline to compare against yet"
    # n/a, not zero — we cannot know what is new without a baseline.
    assert diff["new_links"] is None
    assert diff["removed_links"] is None


def test_first_scan_persists_a_snapshot(db, monkeypatch):
    _install_scrape(monkeypatch, SCAN_1)
    _scan(TestClient(main.app))

    assert len(db.snapshots) == 1
    rows = db.findings["snap-1"]
    # Only flagged items become findings: /b (404) and the dead CTA. /a works.
    assert {r["bucket"] for r in rows} == {"broken", "dead_cta"}
    assert len(rows) == 2


# ─── second scan: new / fixed / recurring ───────────────────────────────────
def _two_scans(db, monkeypatch):
    client = TestClient(main.app)
    _install_scrape(monkeypatch, SCAN_1)
    first = _scan(client)
    _install_scrape(monkeypatch, SCAN_2)
    second = _scan(client)
    return first, second


def test_second_scan_diff_counts(db, monkeypatch):
    _, second = _two_scans(db, monkeypatch)
    diff = second["diff"]

    assert diff["has_baseline"] is True
    assert diff["new"] == 1        # /d is newly broken
    assert diff["fixed"] == 1      # /b is gone
    assert diff["recurring"] == 1  # the dead CTA persists
    assert diff["summary"] == "1 new · 1 fixed · 1 still open"


def test_second_scan_link_counts(db, monkeypatch):
    _, second = _two_scans(db, monkeypatch)
    assert second["diff"]["new_links"] == 1      # /d appeared
    assert second["diff"]["removed_links"] == 1  # /b disappeared


def test_fixed_finding_is_reported_with_its_url(db, monkeypatch):
    _, second = _two_scans(db, monkeypatch)
    fixed = second["diff"]["fixed_findings"]
    assert len(fixed) == 1
    assert fixed[0]["url"] == "https://acme.test/b"
    assert fixed[0]["status"] == "resolved"
    assert fixed[0]["resolved_at"]


def test_fixed_finding_is_stamped_resolved_in_the_store(db, monkeypatch):
    _two_scans(db, monkeypatch)
    rows = db.findings["snap-1"]
    b_row = next(r for r in rows if r["url"] == "https://acme.test/b")
    assert b_row["status"] == "resolved"
    assert b_row["resolved_at"]


def test_results_are_annotated_with_diff_status(db, monkeypatch):
    _, second = _two_scans(db, monkeypatch)
    by_anchor = {r["anchor_text"]: r for r in second["data"]}

    assert by_anchor["D"]["diff_status"] == "new"
    assert by_anchor["Buy Now"]["diff_status"] == "recurring"
    # A working link is not a finding and carries no diff status.
    assert by_anchor["A"]["diff_status"] is None
    assert by_anchor["A"]["priority"] is None


def test_recurring_finding_keeps_its_original_first_seen_at(db, monkeypatch):
    """Age must survive the rerun, or 'broken for N days' resets every scan."""
    first, second = _two_scans(db, monkeypatch)
    cta_first = next(r for r in first["data"] if r["anchor_text"] == "Buy Now")
    cta_second = next(r for r in second["data"] if r["anchor_text"] == "Buy Now")

    assert cta_second["first_seen_at"] == cta_first["first_seen_at"]
    assert cta_second["age_days"] == 0


def test_every_flagged_result_carries_a_fingerprint(db, monkeypatch):
    _, second = _two_scans(db, monkeypatch)
    for item in second["data"]:
        assert item["fingerprint"], item["url"]


def test_rescanning_an_unchanged_page_reports_nothing_new(db, monkeypatch):
    client = TestClient(main.app)
    _install_scrape(monkeypatch, SCAN_1)
    _scan(client)
    diff = _scan(client)["diff"]

    assert diff["new"] == 0
    assert diff["fixed"] == 0
    assert diff["recurring"] == 2
    assert diff["new_links"] == 0 and diff["removed_links"] == 0


# ─── GET /api/sites/{id}/diff/latest ────────────────────────────────────────
def test_diff_endpoint_without_any_scans(db):
    body = TestClient(main.app).get("/api/sites/site-1/diff/latest").json()
    assert body["has_baseline"] is False
    assert body["summary"] == "No scans yet"


def test_diff_endpoint_after_one_scan_has_no_baseline(db, monkeypatch):
    _install_scrape(monkeypatch, SCAN_1)
    _scan(TestClient(main.app))

    body = TestClient(main.app).get("/api/sites/site-1/diff/latest").json()
    assert body["has_baseline"] is False
    assert body["new_links"] is None


def test_diff_endpoint_after_two_scans(db, monkeypatch):
    _two_scans(db, monkeypatch)
    body = TestClient(main.app).get("/api/sites/site-1/diff/latest").json()

    assert body["has_baseline"] is True
    assert body["new"] == 1 and body["fixed"] == 1 and body["recurring"] == 1
    assert body["summary"] == "1 new · 1 fixed · 1 still open"
    assert [i["url"] for i in body["items"]["new"]] == ["https://acme.test/d"]
    assert [i["url"] for i in body["items"]["fixed"]] == ["https://acme.test/b"]
    assert body["items"]["recurring"][0]["bucket"] == "dead_cta"


def test_diff_endpoint_items_carry_age(db, monkeypatch):
    _two_scans(db, monkeypatch)
    body = TestClient(main.app).get("/api/sites/site-1/diff/latest").json()
    for item in body["items"]["recurring"]:
        assert "age_days" in item and isinstance(item["age_days"], int)


def test_scan_survives_a_dead_database(monkeypatch):
    """A DB outage must not fail the scan, and must not claim everything is new."""
    async def boom(*args, **kwargs):
        raise RuntimeError("supabase down")

    for name in ("get_site_id", "get_latest_snapshot", "get_recent_snapshots",
                 "get_findings_for_snapshot", "save_scan", "save_snapshot"):
        monkeypatch.setattr(main, name, boom)

    async def passthrough(results):
        return results

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "process_suggestions", passthrough)
    monkeypatch.setattr(main, "send_slack_notification", noop)
    _install_scrape(monkeypatch, SCAN_1)

    payload = _scan(TestClient(main.app))
    assert payload["type"] == "result"
    assert payload["diff"]["has_baseline"] is False
    assert len(payload["data"]) == 3


# ─── baseline_status: a failed lookup is not a first scan ───────────────────
# The bug this guards: get_latest_snapshot swallowed every exception and
# returned None, which is exactly what "this site has no snapshot" looks like.
# With migrations/001 unapplied, a site scanned fifty times reported
# "No previous scan to compare against" every single time.
def test_first_scan_reports_baseline_status_first_scan(db, monkeypatch):
    _install_scrape(monkeypatch, SCAN_1)
    assert _scan(TestClient(main.app))["diff"]["baseline_status"] == "first_scan"


def test_second_scan_reports_baseline_status_ok(db, monkeypatch):
    _, second = _two_scans(db, monkeypatch)
    assert second["diff"]["baseline_status"] == "ok"


def test_missing_diffing_tables_report_unavailable_not_first_scan(monkeypatch):
    """The scan still succeeds, but it must not pretend it is the first one."""
    async def missing_table(*args, **kwargs):
        raise RuntimeError('relation "scan_snapshots" does not exist')

    async def fake_save_scan(**kwargs):
        return {"site_id": "site-1", "scan_id": "scan-1"}

    async def fake_site_id(*args, **kwargs):
        return "site-1"

    monkeypatch.setattr(main, "get_site_id", fake_site_id)
    monkeypatch.setattr(main, "get_latest_snapshot", missing_table)
    monkeypatch.setattr(main, "save_snapshot", missing_table)
    monkeypatch.setattr(main, "save_scan", fake_save_scan)

    async def passthrough(results):
        return results

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "process_suggestions", passthrough)
    monkeypatch.setattr(main, "send_slack_notification", noop)
    _install_scrape(monkeypatch, SCAN_1)

    payload = _scan(TestClient(main.app))
    assert payload["type"] == "result"          # the scan still succeeds
    assert payload["diff"]["has_baseline"] is False
    assert payload["diff"]["baseline_status"] == "unavailable"


def test_snapshot_write_failure_reports_unavailable(monkeypatch):
    """Reads work, the write fails: the next scan will have no baseline, so say so."""
    async def fake_site_id(*args, **kwargs):
        return "site-1"

    async def no_snapshot(site_id):
        return None

    async def write_fails(*args, **kwargs):
        raise RuntimeError('relation "findings" does not exist')

    async def fake_save_scan(**kwargs):
        return {"site_id": "site-1", "scan_id": "scan-1"}

    monkeypatch.setattr(main, "get_site_id", fake_site_id)
    monkeypatch.setattr(main, "get_latest_snapshot", no_snapshot)
    monkeypatch.setattr(main, "save_snapshot", write_fails)
    monkeypatch.setattr(main, "save_scan", fake_save_scan)

    async def passthrough(results):
        return results

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "process_suggestions", passthrough)
    monkeypatch.setattr(main, "send_slack_notification", noop)
    _install_scrape(monkeypatch, SCAN_1)

    assert _scan(TestClient(main.app))["diff"]["baseline_status"] == "unavailable"


# ─── GET /api/diagnostics/diffing ───────────────────────────────────────────
def test_diagnostics_reports_ready_when_tables_exist(monkeypatch):
    async def ready():
        return {"scan_snapshots": "ok", "findings": "ok"}

    monkeypatch.setattr(main, "diffing_tables_ready", ready)
    body = TestClient(main.app).get("/api/diagnostics/diffing").json()
    assert body["diffing_ready"] is True
    assert "hint" not in body


def test_diagnostics_names_the_missing_table_and_the_migration(monkeypatch):
    async def missing():
        return {"scan_snapshots": "error: relation does not exist", "findings": "ok"}

    monkeypatch.setattr(main, "diffing_tables_ready", missing)
    body = TestClient(main.app).get("/api/diagnostics/diffing").json()
    assert body["diffing_ready"] is False
    assert "scan_snapshots" in body["checks"]
    assert "001" in body["migration"]
    assert "hint" in body


def test_diagnostics_survives_a_dead_database(monkeypatch):
    async def boom():
        raise RuntimeError("supabase_url is required")

    monkeypatch.setattr(main, "diffing_tables_ready", boom)
    body = TestClient(main.app).get("/api/diagnostics/diffing").json()
    assert body["diffing_ready"] is False
    assert "supabase_url" in body["error"]
