"""
Fix verification: re-check one finding, live.

The whole value of this is that it does not take anyone's word for it. If the
link is still broken, it says so. It never flips a finding to "verified_fixed"
on anything other than a clean live check.
"""
import httpx

from checker import check_single
from models import RawLink

VERIFIED = "verified_fixed"
STILL_OPEN = "open"


def _get(finding, field, default=None):
    if isinstance(finding, dict):
        return finding.get(field, default)
    return getattr(finding, field, default)


def _as_raw_link(finding) -> RawLink:
    return RawLink(
        url=_get(finding, "url", "") or "",
        source_element="a",
        anchor_text=_get(finding, "anchor_text", "") or "",
        category=_get(finding, "zone", "") or "Other",
        is_external=False,
    )


async def verify_finding(finding, client: httpx.AsyncClient = None) -> dict:
    """Re-check the finding's URL. Returns the outcome; never mutates the DB.

    A dead CTA has no destination to fetch — nothing to re-check over HTTP, so
    it must be re-scanned rather than verified here. Saying "we cannot confirm
    this from here" is the honest answer, and it matches how the scanner treats
    everything else it cannot prove.
    """
    url = _get(finding, "url", "") or ""
    bucket = _get(finding, "bucket", "") or ""

    if bucket == "dead_cta" or not url.lower().startswith(("http://", "https://")):
        return {
            "verified": False,
            "status": _get(finding, "status", STILL_OPEN) or STILL_OPEN,
            "checked": False,
            "reason": (
                "A button with no destination cannot be re-checked by fetching a "
                "URL. Rescan the page to confirm this one is fixed."
            ),
        }

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(follow_redirects=True, verify=False)
    try:
        result = await check_single(client, _as_raw_link(finding))
    finally:
        if owns_client:
            await client.aclose()

    healthy = result.bucket == "ok"
    return {
        "verified": healthy,
        "status": VERIFIED if healthy else STILL_OPEN,
        "checked": True,
        "status_code": result.status_code,
        "bucket": result.bucket,
        "label": result.label,
        "reason": (
            "Live check passed — this is fixed."
            if healthy else
            result.error or f"Still failing: {result.label} ({result.status_code})"
        ),
    }
