"""SPINE CONTRACT v1 — shared, duplicated verbatim in both repos.

  LinkSpy:   backend/spine_contract.py   (this file)
  Dashboard: src/lib/spine-contract.ts

CONTRACT_CHECKSUM (sha256 of the canonical spec): must match in both files.
Pure + dependency-free (hmac/hashlib only).
"""
import hashlib
import hmac

CONTRACT_CHECKSUM = "175499b1741e8eca5f744350b87327e4d116d77a45fc137a5facb0dab7c57c9d"

SPINE_SCHEMA_VERSION = 1
SPINE_SIG_HEADER = "x-spine-signature"
SPINE_SENT_AT_HEADER = "x-spine-sent-at"
SKEW_MAX_SECONDS = 300

EVENT_TYPES = {
    "READY_FOR_QA": "deliverable.ready_for_qa",
    "QA_COMPLETED": "qa.completed",
    "HEARTBEAT": "heartbeat",
}


def sign(raw_body, secret: str) -> str:
    """HMAC-SHA256(secret, raw_body) → lowercase hex. Signs the EXACT bytes on
    the wire so re-serialization can never break the signature."""
    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def verify(raw_body, secret: str, signature, sent_at, now_seconds: float):
    """Returns (ok: bool, reason: str). Constant-time compare + ±5-min skew."""
    if not signature:
        return False, "missing signature"
    try:
        sent = float(sent_at)
    except (TypeError, ValueError):
        return False, "missing/invalid sent-at"
    if abs(now_seconds - sent) > SKEW_MAX_SECONDS:
        return False, "timestamp skew"
    expected = sign(raw_body, secret)
    if not hmac.compare_digest(expected, str(signature)):
        return False, "bad signature"
    return True, "ok"
