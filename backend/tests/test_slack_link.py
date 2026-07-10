"""
The Slack "View Full Report" button.

It was built as f"{frontend}?url={url}" with the scanned URL pasted in raw. A
URL carries "://" and may carry its own ?query, which terminates ours — Slack
then flags the button and the link lands on an empty scanner.
"""
from urllib.parse import parse_qs, urlsplit

import pytest

import main


def _button_url(scanned: str) -> str:
    from urllib.parse import quote
    return f"{main._frontend_url()}/?url={quote(scanned, safe='')}"


@pytest.mark.parametrize("scanned", [
    "https://www.apexure.com/who-we-are/",
    "https://acme.test/search?q=1&page=2",       # its own query string
    "https://acme.test/a#section",               # its own fragment
    "https://acme.test/path with space",
    "https://acme.test/café",                    # non-ascii
])
def test_scanned_url_round_trips_through_the_button(scanned):
    button = _button_url(scanned)
    query = parse_qs(urlsplit(button).query)
    assert query["url"] == [scanned]


def test_button_has_exactly_one_query_parameter():
    """A raw "?q=1" in the scanned URL used to smuggle extra parameters in."""
    button = _button_url("https://acme.test/search?q=1&page=2")
    assert list(parse_qs(urlsplit(button).query)) == ["url"]


def test_button_points_at_the_frontend_origin(monkeypatch):
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    assert _button_url("https://acme.test/").startswith(main.DEFAULT_FRONTEND_URL)


def test_frontend_url_is_configurable(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://preview.example.com/")
    assert main._frontend_url() == "https://preview.example.com"
    assert _button_url("https://acme.test/").startswith("https://preview.example.com/?url=")


def test_scheme_and_slashes_are_encoded():
    button = _button_url("https://acme.test/")
    assert "https%3A%2F%2F" in button
    # The only unencoded "://" is the frontend's own.
    assert button.count("://") == 1
