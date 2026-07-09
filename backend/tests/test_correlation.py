"""
Console / failed-request correlation.

Correlation is a hypothesis, not evidence. It may append to `reason` and nothing
else — a "possibly caused by" note must never promote an item into a red bucket
or raise its confidence.
"""
import pytest

from correlation import enrich_reasons, page_causes
from models import RawLink


def _dead_cta(reason="Button has no static handler", bucket="dead_cta",
              confidence="high") -> RawLink:
    return RawLink(url="https://acme.test/", source_element="button",
                   anchor_text="Buy Now", category="Dead CTA", is_external=False,
                   link_kind="dead_cta", bucket=bucket, confidence=confidence,
                   reason=reason)


def _broken_link() -> RawLink:
    return RawLink(url="https://acme.test/gone", source_element="a",
                   anchor_text="Gone", category="Body text", is_external=False,
                   bucket="broken", reason="")


SCRIPT_404 = {"http_errors": [{"url": "https://acme.test/js/app.js", "status": 404,
                               "resource_type": "script"}]}
SCRIPT_FAILED = {"failed_requests": [{"url": "https://acme.test/js/app.js",
                                      "resource_type": "script",
                                      "failure": "net::ERR_ABORTED"}]}
IMAGE_404 = {"http_errors": [{"url": "https://acme.test/img/x.png", "status": 404,
                              "resource_type": "image"}]}
CSP = {"csp_violations": ["Refused to execute inline script because of "
                          "Content Security Policy"]}


# ─── page_causes ─────────────────────────────────────────────────────────────
def test_failed_script_is_a_cause():
    assert page_causes(SCRIPT_404) == ["app.js failed to load (404)"]


def test_aborted_script_request_is_a_cause():
    assert page_causes(SCRIPT_FAILED) == ["app.js failed to load"]


def test_a_broken_image_is_not_a_cause_of_a_dead_button():
    """An image 404 does not stop a button working."""
    assert page_causes(IMAGE_404) == []


def test_csp_violation_is_a_cause():
    assert page_causes(CSP) == ["a Content Security Policy rule blocked a script"]


def test_no_signals_means_no_causes():
    assert page_causes({}) == []
    assert page_causes(None) == []


def test_causes_are_deduped():
    signals = {
        "http_errors": [{"url": "https://acme.test/js/app.js", "status": 404,
                         "resource_type": "script"}] * 3,
    }
    assert page_causes(signals) == ["app.js failed to load (404)"]


# ─── enrich_reasons ──────────────────────────────────────────────────────────
def test_dead_cta_reason_names_the_probable_cause():
    cta = _dead_cta()
    assert enrich_reasons([cta], SCRIPT_404) == 1
    assert cta.reason == (
        "Button has no static handler · possibly caused by: app.js failed to load (404)"
    )


def test_enrichment_never_changes_bucket_or_confidence():
    cta = _dead_cta(bucket="unverifiable", confidence="low")
    enrich_reasons([cta], SCRIPT_404)
    assert cta.bucket == "unverifiable"
    assert cta.confidence == "low"


def test_broken_links_are_not_enriched():
    """A 404 explains itself; a broken script did not cause it."""
    link = _broken_link()
    assert enrich_reasons([link], SCRIPT_404) == 0
    assert link.reason == ""


def test_nothing_is_enriched_without_a_cause():
    cta = _dead_cta()
    assert enrich_reasons([cta], IMAGE_404) == 0
    assert "possibly caused by" not in cta.reason


def test_enrichment_is_idempotent():
    """A rescan must not stack the same note twice."""
    cta = _dead_cta()
    enrich_reasons([cta], SCRIPT_404)
    once = cta.reason
    enrich_reasons([cta], SCRIPT_404)
    assert cta.reason == once


def test_at_most_two_causes_are_listed():
    signals = {"http_errors": [
        {"url": f"https://acme.test/js/{n}.js", "status": 404, "resource_type": "script"}
        for n in ("a", "b", "c", "d")
    ]}
    cta = _dead_cta()
    enrich_reasons([cta], signals)
    assert cta.reason.count("failed to load") == 2


def test_enrich_reasons_handles_dict_rows():
    """scan-site works on serialized dicts, not models."""
    row = {"link_kind": "dead_cta", "bucket": "dead_cta", "reason": "Dead button"}
    assert enrich_reasons([row], SCRIPT_404) == 1
    assert "possibly caused by" in row["reason"]


def test_enrich_reasons_tolerates_empty_inputs():
    assert enrich_reasons([], SCRIPT_404) == 0
    assert enrich_reasons(None, SCRIPT_404) == 0
    assert enrich_reasons([_dead_cta()], {}) == 0
