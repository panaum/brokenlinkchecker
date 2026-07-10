"""
Fix verification.

The point of this endpoint is that it does not take anyone's word for it. It
flips a finding to "verified_fixed" only on a clean live check, and when the
link is still broken it says so.
"""
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

import main
from fix_verify import STILL_OPEN, VERIFIED, verify_finding


def _finding(**over) -> dict:
    base = {"id": "f1", "site_id": "site-1", "fingerprint": "fp1",
            "url": "https://acme.test/gone", "anchor_text": "Buy Now",
            "bucket": "broken", "zone": "CTA", "status": "open",
            "first_seen_at": "2026-07-01T00:00:00+00:00"}
    base.update(over)
    return base


def _verify(finding, status: int):
    async def run():
        transport = httpx.MockTransport(lambda req: httpx.Response(status))
        async with httpx.AsyncClient(transport=transport, follow_redirects=True) as c:
            return await verify_finding(finding, c)
    return asyncio.run(run())


# ─── the checker itself ──────────────────────────────────────────────────────
def test_a_healed_link_verifies():
    out = _verify(_finding(), 200)
    assert out["verified"] is True
    assert out["status"] == VERIFIED
    assert out["checked"] is True


def test_a_still_broken_link_does_not_lie():
    out = _verify(_finding(), 404)
    assert out["verified"] is False
    assert out["status"] == STILL_OPEN
    assert "404" in out["reason"] or "broken" in out["reason"].lower()


def test_an_unverifiable_response_is_not_treated_as_fixed():
    """A 403 proves nothing. Claiming "fixed" here would be the whole bug."""
    out = _verify(_finding(), 403)
    assert out["verified"] is False
    assert out["status"] == STILL_OPEN


def test_a_dead_cta_cannot_be_verified_by_fetching_a_url():
    out = _verify(_finding(bucket="dead_cta", url="https://acme.test/page"), 200)
    assert out["verified"] is False
    assert out["checked"] is False
    assert "rescan" in out["reason"].lower()


def test_a_non_http_finding_is_not_fetched():
    out = _verify(_finding(url="mailto:hi@acme.test"), 200)
    assert out["checked"] is False


# ─── the endpoint ────────────────────────────────────────────────────────────
@pytest.fixture
def client(monkeypatch):
    state = {"verified": None}

    async def get_finding(finding_id, site_id=""):
        return _finding(id=finding_id) if finding_id == "f1" else None

    async def get_site_url(site_id):
        return "https://acme.test"

    async def mark_verified(finding_id, resolved_at):
        state["verified"] = (finding_id, resolved_at)
        return {}

    monkeypatch.setattr(main, "get_finding", get_finding)
    monkeypatch.setattr(main, "get_site_url", get_site_url)
    monkeypatch.setattr(main, "mark_finding_verified", mark_verified)
    return TestClient(main.app), state


def _stub_verify(monkeypatch, outcome):
    async def fake(finding, client=None):
        return outcome
    monkeypatch.setattr(main, "verify_finding", fake)


def test_verify_endpoint_flips_status_and_stamps_resolved_at(client, monkeypatch):
    app, state = client
    _stub_verify(monkeypatch, {"verified": True, "status": VERIFIED, "checked": True,
                               "reason": "Live check passed — this is fixed."})

    body = app.post("/api/findings/f1/verify").json()
    assert body["verified"] is True
    assert body["status"] == VERIFIED
    assert body["resolved_at"]
    assert state["verified"][0] == "f1"


def test_verify_endpoint_does_not_mark_a_still_broken_finding(client, monkeypatch):
    app, state = client
    _stub_verify(monkeypatch, {"verified": False, "status": STILL_OPEN, "checked": True,
                               "reason": "Still failing: broken (404)"})

    body = app.post("/api/findings/f1/verify").json()
    assert body["verified"] is False
    assert body["status"] == STILL_OPEN
    assert "resolved_at" not in body
    assert state["verified"] is None


def test_verify_endpoint_404s_on_an_unknown_finding(client):
    app, _ = client
    assert app.post("/api/findings/nope/verify").status_code == 404


def test_a_failed_write_never_claims_the_fix_was_recorded(client, monkeypatch):
    """The link is fixed, but we could not save that. Do not say we did."""
    app, _ = client
    _stub_verify(monkeypatch, {"verified": True, "status": VERIFIED, "checked": True,
                               "reason": "ok"})

    async def write_fails(finding_id, resolved_at):
        raise RuntimeError("row-level security policy")

    monkeypatch.setattr(main, "mark_finding_verified", write_fails)

    body = app.post("/api/findings/f1/verify").json()
    assert body["verified"] is False
    assert "recording that failed" in body["reason"]


# ─── the fix + client-message endpoints ─────────────────────────────────────
def test_fix_endpoint_returns_hand_authored_steps(client):
    app, _ = client
    body = app.get("/api/findings/f1/fix", params={"builder": "Elementor"}).json()
    assert body["template_source"] == "fix_templates/elementor.yaml"
    assert body["steps"]
    assert "{" not in " ".join(body["steps"])


def test_client_message_endpoint_escapes_and_renders(client):
    app, _ = client
    body = app.get("/api/findings/f1/client-message").json()
    assert body["subject"] and body["body"]
    assert "{" not in body["body"]


def test_client_message_mentions_how_long_it_has_been_broken(client):
    app, _ = client
    body = app.get("/api/findings/f1/client-message").json()
    assert "day" in body["body"]


# ─── the fix-pack endpoint ──────────────────────────────────────────────────
def test_fix_pack_endpoint_returns_a_zip(monkeypatch):
    import io, zipfile

    async def latest_snapshot(site_id):
        return {"id": "snap-1", "totals_json": {
            "detected_builders": ["Elementor"],
            "redirect_rules": [{"from": "https://acme.test/old",
                                "to": "https://acme.test/new", "status": 301, "hops": 1}],
        }}

    async def findings(snapshot_id):
        return [
            _finding(url="https://acme.test/gone"),
            {**_finding(url="https://acme.test/about-us"), "bucket": "ok"},
        ]

    async def site_url(site_id):
        return "https://acme.test"

    monkeypatch.setattr(main, "get_latest_snapshot", latest_snapshot)
    monkeypatch.setattr(main, "get_findings_for_snapshot", findings)
    monkeypatch.setattr(main, "get_site_url", site_url)

    resp = TestClient(main.app).get("/api/sites/site-1/fix-pack")
    assert resp.status_code == 200
    assert "linkspy-fix-pack.zip" in resp.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = set(zf.namelist())
        md = zf.read("instructions.md").decode("utf-8")
    assert {"README.txt", "fixes.csv", "instructions.md"} <= names
    assert any(n.startswith("redirects/") for n in names)
    assert "Elementor" in md
    # Working links are not findings and must not appear as work to do.
    assert "about-us" not in md


def test_fix_pack_endpoint_404s_before_any_scan(monkeypatch):
    async def no_snapshot(site_id):
        return None

    async def site_url(site_id):
        return "https://acme.test"

    monkeypatch.setattr(main, "get_latest_snapshot", no_snapshot)
    monkeypatch.setattr(main, "get_site_url", site_url)
    resp = TestClient(main.app).get("/api/sites/site-1/fix-pack")
    assert resp.status_code == 404
