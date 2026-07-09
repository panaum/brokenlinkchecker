"""
Console / failed-request correlation.

A dead CTA on a page whose app.js 404'd is almost certainly dead *because* of
that. Saying so turns "this button does nothing" into "this button does nothing,
and here is why".

Strictly additive: this only ever appends to `reason`. It never changes bucket,
confidence, label or priority. A correlation is a hypothesis ("possibly caused
by"), and a hypothesis must not promote an item into a red bucket.
"""
import posixpath
from urllib.parse import urlparse

# Resource kinds whose failure plausibly breaks a button or a link.
_BEHAVIOUR_RESOURCES = frozenset({"script", "xhr", "fetch"})

MAX_CAUSES = 2


def _basename(url: str) -> str:
    path = urlparse(url).path
    return posixpath.basename(path) or urlparse(url).netloc or url


def _get(result, field, default=None):
    if isinstance(result, dict):
        return result.get(field, default)
    return getattr(result, field, default)


def _set_reason(result, reason: str) -> None:
    if isinstance(result, dict):
        result["reason"] = reason
    else:
        result.reason = reason


def page_causes(signals: dict) -> list:
    """Human-readable causes observed on the page, most specific first.

    A failed <script> beats a generic console error: it explains the symptom.
    """
    signals = signals or {}
    causes = []

    for error in signals.get("http_errors", []):
        if error.get("resource_type") in _BEHAVIOUR_RESOURCES:
            causes.append(f"{_basename(error['url'])} failed to load ({error['status']})")

    for failure in signals.get("failed_requests", []):
        if failure.get("resource_type") in _BEHAVIOUR_RESOURCES:
            causes.append(f"{_basename(failure['url'])} failed to load")

    if signals.get("csp_violations"):
        causes.append("a Content Security Policy rule blocked a script")

    # Dedupe, preserve order.
    seen, unique = set(), []
    for cause in causes:
        if cause not in seen:
            seen.add(cause)
            unique.append(cause)
    return unique


def enrich_reasons(results, signals: dict) -> int:
    """Append "possibly caused by: …" to flagged items on a page that had a
    behaviour-breaking failure. Returns how many items were enriched.

    Only dead CTAs and unverifiable dead-CTA candidates are enriched: a 404 on a
    link is explained by its own status code, not by a broken script.
    """
    causes = page_causes(signals)
    if not causes:
        return 0

    suffix = " · possibly caused by: " + "; ".join(causes[:MAX_CAUSES])
    enriched = 0

    for result in results or []:
        if _get(result, "link_kind") != "dead_cta":
            continue
        bucket_before = _get(result, "bucket")
        reason = _get(result, "reason") or ""
        if "possibly caused by:" in reason:
            continue

        _set_reason(result, reason + suffix)
        enriched += 1

        # Guard the invariant rather than trust it: correlation is a hypothesis
        # and must never move an item into a red bucket.
        assert _get(result, "bucket") == bucket_before

    return enriched
