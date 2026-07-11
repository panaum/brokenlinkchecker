"""Share-token helpers — pure, no I/O.

A share token is a capability: unguessable (256 bits of entropy) and URL-safe.
Holding it grants read-only access to exactly one scan's public report.
"""
import secrets


def new_token() -> str:
    """32 random bytes, URL-safe base64 (~43 chars). Unguessable."""
    return secrets.token_urlsafe(32)


def is_wellformed(token: str) -> bool:
    """Cheap shape check before a DB lookup — rejects obviously-bogus tokens
    without a round trip. Real authorization is the row lookup + revoked flag."""
    if not token or len(token) < 20 or len(token) > 128:
        return False
    return all(c.isalnum() or c in "-_" for c in token)
