"""Invite accept flow — the public, credential-bearing endpoint.

Covers malformed tokens, the revoked/used/expired rejections, and that a
successful accept mints a portal token that actually verifies to the invited
email (no NextAuth involved).
"""
import pytest
from fastapi.testclient import TestClient

import main
import database
import auth


SECRET = "a-proper-test-secret-long-enough"
GOOD = "a" * 32  # well-formed token shape


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("BACKEND_AUTH_SECRET", SECRET)
    monkeypatch.delenv("NEXTAUTH_SECRET", raising=False)


@pytest.fixture
def client():
    return TestClient(main.app)


def test_malformed_token_is_404(client):
    r = client.post("/api/invites/short/accept")
    assert r.status_code == 404


@pytest.mark.parametrize("reason,code,word", [
    ("revoked", 400, "revoked"),
    ("used", 400, "used"),
    ("expired", 400, "expired"),
    ("not_found", 404, "invalid"),
    ("storage_unavailable", 400, "migration"),
])
def test_rejections_map_to_clear_errors(client, monkeypatch, reason, code, word):
    async def fake_accept(_t, _n):
        return {"reason": reason}
    monkeypatch.setattr(database, "accept_invite", fake_accept)
    r = client.post(f"/api/invites/{GOOD}/accept")
    assert r.status_code == code
    assert word in r.json()["error"].lower()


def test_success_mints_a_verifiable_portal_token(client, monkeypatch):
    async def fake_accept(_t, _n):
        return {"email": "viewer@client.com", "workspace_id": "W",
                "client_id": "CA", "role": "client_viewer"}
    async def fake_audit(*_a, **_k):
        return None
    monkeypatch.setattr(database, "accept_invite", fake_accept)
    monkeypatch.setattr(database, "write_audit", fake_audit)

    r = client.post(f"/api/invites/{GOOD}/accept")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "viewer@client.com"
    # The minted token verifies back to the invited email — that's the login.
    assert auth.verify_token(body["token"]) == "viewer@client.com"
