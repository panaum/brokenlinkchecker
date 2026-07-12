"""CRM credentials must round-trip encrypted and never leak in logs/errors."""
import tracer_crypto

# Deliberately NOT in any real vendor token format — this is fake test data and
# must not trip secret scanners. It still exercises the crypto + the redactor
# (matches redact's long-secret branch).
FAKE_TOKEN = "EXAMPLE-crm-credential-do-not-use-abcdef0123456789abcdef"


def test_encrypt_round_trip(monkeypatch):
    monkeypatch.setenv("BACKEND_AUTH_SECRET", "unit-test-secret-value")
    enc = tracer_crypto.encrypt(FAKE_TOKEN)
    assert enc != FAKE_TOKEN and FAKE_TOKEN not in enc     # ciphertext, not plaintext
    assert tracer_crypto.decrypt(enc) == FAKE_TOKEN


def test_redact_scrubs_long_secrets():
    msg = f"auth failed for Bearer {FAKE_TOKEN} on request"
    out = tracer_crypto.redact(msg)
    assert FAKE_TOKEN not in out and "[redacted]" in out
