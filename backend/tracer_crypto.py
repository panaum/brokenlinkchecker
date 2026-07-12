"""At-rest encryption for CRM credentials + hard redaction.

CRM tokens are the crown jewels: a leaked HubSpot private-app token or GHL
location key exposes a client's whole CRM. They are encrypted before they ever
touch the database and NEVER logged. Every error path that might carry a token
runs through redact() first.

Key: TRACER_CRYPTO_KEY (a Fernet key) if set; otherwise derived deterministically
from the existing BACKEND_AUTH_SECRET / NEXTAUTH_SECRET so there is no new secret
to provision, and rotating that secret rotates the encryption.
"""
import base64
import hashlib
import os
import re


def _fernet():
    from cryptography.fernet import Fernet
    key = os.getenv("TRACER_CRYPTO_KEY", "").strip()
    if key:
        return Fernet(key.encode())
    secret = (os.getenv("BACKEND_AUTH_SECRET") or os.getenv("NEXTAUTH_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("No encryption key: set TRACER_CRYPTO_KEY or BACKEND_AUTH_SECRET.")
    derived = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(derived)


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        plaintext = ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    if not token:
        return ""
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")


# Anything that looks like a bearer token / long secret, plus known CRM shapes.
_SECRET_RE = re.compile(
    r"(pat-[a-z0-9-]{8,}|eyJ[\w-]{10,}|Bearer\s+[\w.\-]{10,}|[A-Za-z0-9_\-]{32,})", re.I)


def redact(text) -> str:
    """Scrub anything token-shaped from a string before it is logged or returned."""
    if text is None:
        return ""
    return _SECRET_RE.sub("[redacted]", str(text))
