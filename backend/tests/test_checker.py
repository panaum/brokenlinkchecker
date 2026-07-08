"""
Bot-block detection + status classification tests.
"""
import httpx
import pytest

from checker import _is_bot_blocked, classify


def _resp(status=200, body="", headers=None):
    return httpx.Response(
        status_code=status,
        headers=headers or {},
        content=body.encode("utf-8"),
    )


# ─── Healthy 200 pages that must NOT be treated as bot-blocked ────────────────
def test_meta_robots_not_blocked():
    body = '<html><head><meta name="robots" content="index,follow"></head><body>Hi</body></html>'
    assert _is_bot_blocked(_resp(200, body)) is False


def test_automated_marketing_copy_not_blocked():
    body = "<html><body>Our automated workflows save you hours every week.</body></html>"
    assert _is_bot_blocked(_resp(200, body)) is False


def test_recaptcha_script_not_blocked():
    body = '<html><body><script src="https://www.google.com/recaptcha/api.js"></script>Contact us</body></html>'
    assert _is_bot_blocked(_resp(200, body)) is False


def test_blocked_word_in_copy_not_blocked():
    body = "<html><body>Nothing here is blocked or restricted. Enjoy!</body></html>"
    assert _is_bot_blocked(_resp(200, body)) is False


# ─── Genuine challenge / block responses that MUST be blocked ─────────────────
def test_cloudflare_just_a_moment_403_blocked():
    body = "<html><head><title>Just a moment...</title></head><body>Checking your browser</body></html>"
    assert _is_bot_blocked(_resp(403, body)) is True


def test_cloudflare_server_503_blocked():
    assert _is_bot_blocked(_resp(503, "server error", headers={"server": "cloudflare"})) is True


def test_cf_mitigated_header_blocked():
    assert _is_bot_blocked(_resp(403, "", headers={"cf-mitigated": "challenge"})) is True


def test_px_captcha_403_blocked():
    body = "<html><body>px-captcha challenge required</body></html>"
    assert _is_bot_blocked(_resp(403, body)) is True


# ─── classify() ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("status,expected", [
    (200, "ok"),
    (204, "ok"),
    (301, "redirect"),
    (302, "redirect"),
    (401, "blocked"),
    (403, "blocked"),
    (405, "blocked"),
    (429, "blocked"),
    (999, "blocked"),
    (404, "broken"),
    (410, "broken"),
    (500, "error"),
    (503, "error"),
    (None, "timeout"),
])
def test_classify(status, expected):
    assert classify(status) == expected
