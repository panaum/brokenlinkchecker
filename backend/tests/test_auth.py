"""Auth core: token verification + role logic (the security primitives).

The full cross-scope 403 suite comes once routes are wrapped; these lock the
verification + role math that the whole layer rests on.
"""
import asyncio

import jwt
import pytest

import auth


SECRET = "test-secret-please-change"


@pytest.fixture(autouse=True)
def _set_secret(monkeypatch):
    monkeypatch.setenv("BACKEND_AUTH_SECRET", SECRET)
    monkeypatch.delenv("NEXTAUTH_SECRET", raising=False)


def _mint(payload, secret=SECRET):
    return jwt.encode(payload, secret, algorithm="HS256")


def test_valid_token_returns_lowercased_email():
    tok = _mint({"email": "Anaum.Pandit@Apexure.com"})
    assert auth.verify_token(tok) == "anaum.pandit@apexure.com"


def test_forged_token_wrong_secret_is_rejected():
    tok = _mint({"email": "attacker@evil.com"}, secret="not-the-secret")
    assert auth.verify_token(tok) is None


def test_expired_token_is_rejected():
    tok = _mint({"email": "x@apexure.com", "exp": 1})  # 1970
    assert auth.verify_token(tok) is None


def test_garbage_and_empty_tokens_are_rejected():
    assert auth.verify_token("") is None
    assert auth.verify_token("not.a.jwt") is None
    assert auth.verify_token(_mint({"no_email": True})) is None


def test_no_secret_configured_rejects_everything(monkeypatch):
    monkeypatch.delenv("BACKEND_AUTH_SECRET", raising=False)
    monkeypatch.delenv("NEXTAUTH_SECRET", raising=False)
    assert auth.verify_token(_mint({"email": "x@apexure.com"})) is None


def test_role_satisfies_rank_order():
    assert auth.role_satisfies("owner", "member")
    assert auth.role_satisfies("member", "member")
    assert auth.role_satisfies("member", "client_viewer")
    assert not auth.role_satisfies("client_viewer", "member")
    assert not auth.role_satisfies(None, "client_viewer")
    assert not auth.role_satisfies("", "member")


def test_is_staff():
    assert auth.is_staff("anaum.pandit@apexure.com")
    assert auth.is_staff("ANYONE@APEXURE.COM")
    assert not auth.is_staff("client@gmail.com")
    assert not auth.is_staff("")


def test_authorize_scope_401_without_email():
    with pytest.raises(auth.HTTPException) as e:
        asyncio.run(auth._authorize_scope(None, {"workspace_id": "w"}, "member"))
    assert e.value.status_code == 401


def test_authorize_scope_404_when_site_has_no_workspace():
    with pytest.raises(auth.HTTPException) as e:
        asyncio.run(auth._authorize_scope("x@apexure.com", None, "member"))
    assert e.value.status_code == 404
    with pytest.raises(auth.HTTPException) as e2:
        asyncio.run(auth._authorize_scope("x@apexure.com", {"workspace_id": None}, "member"))
    assert e2.value.status_code == 404
