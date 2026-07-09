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
    priority: str = "low"  # "critical" | "high" | "medium" | "low"
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


class SiteCreate(BaseModel):
    url: str
    name: str
    client: str
    freq: str
    user_email: str
