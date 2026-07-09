from pydantic import BaseModel
from typing import Optional


class RawLink(BaseModel):
    url: str
    source_element: str
    anchor_text: str
    category: str
    is_external: bool
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
