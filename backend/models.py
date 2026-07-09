from pydantic import BaseModel, Field
from typing import Optional


class RawLink(BaseModel):
    url: str
    source_element: str
    anchor_text: str
    # Primary (highest-priority) zone this URL was found in. A URL linked from
    # several zones — the classic nav + footer pair — is checked once; `zones`
    # keeps the full list so the footer occurrence is not lost.
    category: str
    is_external: bool
    zones: list[str] = Field(default_factory=list)
    occurrences: int = 1
    # "http"    — fetched over the network
    # "anchor"  — in-page #fragment, resolved against the rendered DOM
    # "contact" — mailto:/tel:/sms:, syntax-checked but never fetched
    # "dead_cta"— flagged by the detector, has no destination to check
    link_kind: str = "http"
    # For link_kind == "anchor"/"http": the #fragment part, if any.
    fragment: str = ""
    # What kind of thing this URL is: anchor | image | script | stylesheet |
    # css_url | iframe | media | meta_image | favicon | other. A broken script
    # or stylesheet breaks the page while it still returns HTTP 200.
    resource_type: str = "anchor"
    # "critical" | "high" | "medium" | "low", or None for a working link.
    # Priority is a triage signal, so it is only meaningful for flagged items;
    # the checker clears it once a link comes back healthy (bucket == "ok").
    priority: Optional[str] = "low"
    confidence: str = "high"  # "high" | "medium" | "low"
    reason: str = ""          # human-readable explanation for the flag
    # "broken"       = provable failure (404/410/5xx, DNS, connection refused)
    # "dead_cta"     = CTA-styled element that leads nowhere useful
    # "unverifiable" = cannot judge from here (401/403/429/999, timeouts,
    #                  JS-hydrated subtrees, low-confidence candidates)
    # When unsure, an item belongs in "unverifiable" — never in a red bucket.
    bucket: str = "broken"


class LinkResult(RawLink):
    status_code: Optional[int] = None
    label: str  # ok | broken | redirect | forbidden | timeout | error
    final_url: Optional[str] = None
    response_ms: int = 0
    error: Optional[str] = None
    suggestion: Optional[dict] = None
    impact: Optional[dict] = None
    first_seen_at: Optional[str] = None
    days_broken: Optional[int] = None
    # Phase 1 — baseline diffing. Populated for flagged items only; a working
    # link is not a finding and has no diff status.
    fingerprint: Optional[str] = None
    diff_status: Optional[str] = None   # "new" | "recurring" | None
    age_days: Optional[int] = None
    # Phase 3 — redirect forensics. The full hop chain [{url, status}, …],
    # ending at the final response. Informational: a redirect is not a failure.
    redirect_chain: list[dict] = Field(default_factory=list)
    redirect_flags: list[str] = Field(default_factory=list)


class SiteCreate(BaseModel):
    url: str
    name: str
    client: str
    freq: str
    user_email: str


# ─── Phase 1: baseline diffing ───────────────────────────────────────────────
class FindingRecord(BaseModel):
    """One flagged item, identified across scans by its fingerprint."""
    fingerprint: str
    bucket: str                      # broken | dead_cta | unverifiable
    confidence: str = "high"
    url: str
    anchor_text: str = ""
    zone: str = ""
    reason: str = ""
    # When this finding was first observed — carried forward across scans so an
    # issue's age survives a rerun. Never reset on a recurring finding.
    first_seen_at: Optional[str] = None
    resolved_at: Optional[str] = None
    status: str = "open"             # open | resolved | verified_fixed


class ScanDiff(BaseModel):
    """Result of comparing this scan's findings against the previous snapshot.

    `has_baseline` is False on a site's first scan: the UI shows "n/a" rather
    than reporting every pre-existing issue as new.
    """
    has_baseline: bool = False
    new: list[FindingRecord] = Field(default_factory=list)
    recurring: list[FindingRecord] = Field(default_factory=list)
    fixed: list[FindingRecord] = Field(default_factory=list)
