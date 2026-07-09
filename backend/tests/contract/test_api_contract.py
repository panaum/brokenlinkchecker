"""
API contract snapshot.

This locks the shape of the /scan response as it exists today. Every later
phase is additive: new fields may appear, but nothing here may disappear or
change type. If a change breaks this file, it is a breaking API change and the
frontend (and any other consumer) must be updated deliberately.

The scrape and network layers are stubbed — this test asserts the contract, not
the crawler.
"""
import json

import pytest
from fastapi.testclient import TestClient

import main
from models import LinkResult, RawLink


# ─── Fields the API has always returned. Additive-only from here. ────────────
REQUIRED_RESULT_FIELDS: dict = {
    "url": str,
    "source_element": str,
    "anchor_text": str,
    "category": str,
    "is_external": bool,
    "status_code": (int, type(None)),
    "label": str,
    "final_url": (str, type(None)),
    "response_ms": int,
    "error": (str, type(None)),
    "suggestion": (dict, type(None)),
    "impact": (dict, type(None)),
    "first_seen_at": (str, type(None)),
    "days_broken": (int, type(None)),
    # triage taxonomy
    "priority": (str, type(None)),
    "confidence": str,
    "reason": str,
    "bucket": str,
    # link accounting
    "zones": list,
    "occurrences": int,
    "link_kind": str,
    "fragment": str,
}

REQUIRED_TOP_LEVEL_FIELDS: dict = {
    "type": str,
    "data": list,
    "health_score": int,
    "detected_builders": list,
    "total_links": int,
    "total_placements": int,
}


def _raw(**over) -> RawLink:
    fields = dict(
        url="https://acme.test/page",
        source_element="a",
        anchor_text="Link",
        category="Body text",
        is_external=False,
    )
    fields.update(over)
    return RawLink(**fields)


# One of each kind the pipeline can emit: a healthy link, a broken one,
# a dead CTA, and an unverifiable one.
FIXTURE_LINKS = [
    _raw(url="https://acme.test/ok", category="Navigation", priority="critical"),
    _raw(url="https://acme.test/gone", category="Footer", priority="medium"),
    _raw(url="https://acme.test/", category="Dead CTA", anchor_text="Buy Now",
         priority="medium", confidence="high", bucket="dead_cta",
         reason="Anchor href goes nowhere", link_kind="dead_cta"),
    _raw(url="https://acme.test/blocked", category="CTA", priority="high"),
]

_STATUS_BY_PATH = {"/ok": 200, "/gone": 404, "/blocked": 403}


@pytest.fixture
def client(monkeypatch):
    async def fake_scrape(url):
        return list(FIXTURE_LINKS), ["Elementor"]

    async def fake_check_all(links):
        import httpx
        from checker import check_single

        def handler(request):
            return httpx.Response(_STATUS_BY_PATH.get(request.url.path, 200))

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as c:
            for i, link in enumerate(links, start=1):
                yield i, await check_single(c, link)

    async def fake_save_scan(**kwargs):
        return {}

    async def fake_suggestions(results):
        return results

    async def fake_slack(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "scrape_links", fake_scrape)
    monkeypatch.setattr(main, "check_all_links", fake_check_all)
    monkeypatch.setattr(main, "save_scan", fake_save_scan)
    monkeypatch.setattr(main, "process_suggestions", fake_suggestions)
    monkeypatch.setattr(main, "send_slack_notification", fake_slack)
    return TestClient(main.app)


def _result_event(client) -> dict:
    with client.stream("GET", "/scan", params={"url": "https://acme.test/"}) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            payload = json.loads(line[len("data: "):])
            if payload.get("type") == "result":
                return payload
    raise AssertionError("no 'result' event in the SSE stream")


def _assert_type(value, expected, where):
    if isinstance(expected, tuple):
        assert isinstance(value, expected), f"{where}: {type(value).__name__} not in {expected}"
    else:
        # bool is a subclass of int — never let one satisfy the other.
        assert type(value) is expected or isinstance(value, expected), \
            f"{where}: expected {expected.__name__}, got {type(value).__name__}"


def test_scan_returns_a_result_event(client):
    assert _result_event(client)["type"] == "result"


def test_top_level_response_shape(client):
    payload = _result_event(client)
    for field, expected in REQUIRED_TOP_LEVEL_FIELDS.items():
        assert field in payload, f"missing top-level field: {field}"
        _assert_type(payload[field], expected, field)


def test_every_result_item_carries_the_full_contract(client):
    items = _result_event(client)["data"]
    assert items, "expected result items"
    for item in items:
        for field, expected in REQUIRED_RESULT_FIELDS.items():
            assert field in item, f"missing field {field!r} on {item.get('url')}"
            _assert_type(item[field], expected, f"{item.get('url')}.{field}")


def test_result_items_match_the_linkresult_model(client):
    """The wire format must still deserialize into LinkResult."""
    for item in _result_event(client)["data"]:
        LinkResult(**item)


def test_bucket_is_always_one_of_the_taxonomy(client):
    allowed = {"broken", "dead_cta", "unverifiable", "ok"}
    for item in _result_event(client)["data"]:
        assert item["bucket"] in allowed, item["bucket"]


def test_confidence_is_always_one_of_the_taxonomy(client):
    for item in _result_event(client)["data"]:
        assert item["confidence"] in {"high", "medium", "low"}


# ─── Phase 0: priority is returned ONLY for flagged items ────────────────────
def test_working_links_have_no_priority(client):
    working = [i for i in _result_event(client)["data"] if i["bucket"] == "ok"]
    assert working, "fixture should contain at least one working link"
    for item in working:
        assert item["priority"] is None, f"{item['url']} -> {item['priority']!r}"


def test_flagged_items_keep_their_priority(client):
    flagged = [i for i in _result_event(client)["data"] if i["bucket"] != "ok"]
    assert flagged, "fixture should contain flagged items"
    for item in flagged:
        assert item["priority"] in {"critical", "high", "medium", "low"}, \
            f"{item['url']} -> {item['priority']!r}"


def test_health_endpoint_still_responds(client):
    assert client.get("/health").status_code == 200
