from pydantic import BaseModel
from typing import Optional


class RawLink(BaseModel):
    url: str
    source_element: str
    anchor_text: str
    category: str
    is_external: bool
    priority: str = "low"  # "critical" | "high" | "medium" | "low"


class LinkResult(RawLink):
    status_code: Optional[int] = None
    label: str  # ok | broken | redirect | forbidden | timeout | error
    final_url: Optional[str] = None
    response_ms: int = 0
    error: Optional[str] = None
    suggestion: Optional[dict] = None
