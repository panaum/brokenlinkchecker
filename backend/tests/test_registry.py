"""Phase 1A — Registry API: service-key auth, not_provisioned (503), external_ref
conflict (409), and list shapes. DB layer is monkeypatched (no live Supabase)."""
import pytest
from fastapi.testclient import TestClient

import main
import database

client = TestClient(main.app)
AUTH = {"Authorization": "Bearer goodkey"}


@pytest.fixture(autouse=True)
def _fake_auth(monkeypatch):
    async def fake_verify(raw):
        return {"id": "k1"} if raw == "goodkey" else None
    monkeypatch.setattr(database, "qa_key_verify", fake_verify)


# ── auth ──
def test_clients_requires_key():
    assert client.get("/api/registry/clients").status_code == 401


def test_bad_key_rejected():
    assert client.get("/api/registry/clients", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_clients_list_shape(monkeypatch):
    async def fake(search=None):
        assert search == "acme"          # search is threaded through
        return [{"id": "c1", "name": "Acme"}]
    monkeypatch.setattr(database, "registry_clients", fake)
    r = client.get("/api/registry/clients?search=acme", headers=AUTH)
    assert r.status_code == 200 and r.json()["clients"][0]["name"] == "Acme"


def test_client_sites_shape(monkeypatch):
    async def fake(cid):
        return [{"id": "s1", "name": "LP", "url": "https://acme.co/lp"}]
    monkeypatch.setattr(database, "registry_client_sites", fake)
    r = client.get("/api/registry/clients/c1/sites", headers=AUTH)
    assert r.status_code == 200 and r.json()["sites"][0]["id"] == "s1"


# ── POST deliverables: validation / provisioning / conflict / success ──
def test_create_validates_input(monkeypatch):
    async def fake(*a, **k):
        return {"id": "d1"}
    monkeypatch.setattr(database, "registry_insert_deliverable", fake)
    # bad kind
    r = client.post("/api/registry/deliverables", headers=AUTH,
                    json={"site_id": "s1", "kind": "widget", "name": "x"})
    assert r.status_code == 400
    # missing name
    r = client.post("/api/registry/deliverables", headers=AUTH, json={"site_id": "s1", "kind": "page"})
    assert r.status_code == 400


def test_create_not_provisioned_503(monkeypatch):
    async def fake(*a, **k):
        return dict(database.REGISTRY_NOT_PROVISIONED)
    monkeypatch.setattr(database, "registry_insert_deliverable", fake)
    r = client.post("/api/registry/deliverables", headers=AUTH,
                    json={"site_id": "s1", "kind": "page", "name": "LP", "external_ref": "p1"})
    assert r.status_code == 503 and r.json()["registry"] == "not_provisioned"


def test_create_conflict_409(monkeypatch):
    async def fake(*a, **k):
        return dict(database.REGISTRY_CONFLICT)
    monkeypatch.setattr(database, "registry_insert_deliverable", fake)
    r = client.post("/api/registry/deliverables", headers=AUTH,
                    json={"site_id": "s1", "kind": "page", "name": "LP", "external_ref": "p1"})
    assert r.status_code == 409 and r.json().get("conflict") is True


def test_create_success(monkeypatch):
    async def fake(site_id, kind, name, external_ref=None, url=None):
        return {"id": "d1", "site_id": site_id, "kind": kind, "name": name,
                "external_ref": external_ref, "url": url}
    monkeypatch.setattr(database, "registry_insert_deliverable", fake)
    r = client.post("/api/registry/deliverables", headers=AUTH,
                    json={"site_id": "s1", "kind": "page", "name": "LP",
                          "external_ref": "p1", "url": "https://acme.co/lp"})
    assert r.status_code == 200
    d = r.json()["deliverable"]
    assert d["external_ref"] == "p1" and d["kind"] == "page"


# ── GET deliverables by external_ref: found / not-found / not_provisioned ──
def test_get_deliverable_found(monkeypatch):
    async def fake(ref):
        return {"id": "d1", "external_ref": ref}
    monkeypatch.setattr(database, "registry_get_deliverable", fake)
    r = client.get("/api/registry/deliverables?external_ref=p1", headers=AUTH)
    assert r.status_code == 200 and r.json()["deliverable"]["id"] == "d1"


def test_get_deliverable_none(monkeypatch):
    async def fake(ref):
        return None
    monkeypatch.setattr(database, "registry_get_deliverable", fake)
    r = client.get("/api/registry/deliverables?external_ref=missing", headers=AUTH)
    assert r.status_code == 200 and r.json()["deliverable"] is None


def test_get_deliverable_not_provisioned(monkeypatch):
    async def fake(ref):
        return dict(database.REGISTRY_NOT_PROVISIONED)
    monkeypatch.setattr(database, "registry_get_deliverable", fake)
    r = client.get("/api/registry/deliverables?external_ref=p1", headers=AUTH)
    assert r.status_code == 503
