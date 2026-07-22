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


class FixSuggestion(BaseModel):
    """A deterministic fix for one finding. Produced by fix_engine, never by a
    model: a client follows these steps on a live page."""
    finding_id: str
    issue_type: str          # broken_link | dead_cta | redirect_chain |
                             # mixed_content | missing_asset | external_down
    fix_type: str
    # None when the fix needs a human decision. Always validated before it is
    # written into a CSV, a markdown file, or a code change.
    proposed_value: Optional[str] = None
    title: str = ""
    steps: list[str] = Field(default_factory=list)
    instructions: str = ""
    est_time_minutes: int = 10
    requires_dev: bool = False
    # Describes the PROPOSED VALUE, not the instructions. The steps are always
    # trustworthy; the suggested replacement may be a near-miss.
    confidence: str = "low"
    match_score: int = 0
    builder: str = "Generic"
    template_source: str = ""


class ScanDiff(BaseModel):
    """Result of comparing this scan's findings against the previous snapshot.

    `has_baseline` is False on a site's first scan: the UI shows "n/a" rather
    than reporting every pre-existing issue as new.
    """
    has_baseline: bool = False
    new: list[FindingRecord] = Field(default_factory=list)
    recurring: list[FindingRecord] = Field(default_factory=list)
    fixed: list[FindingRecord] = Field(default_factory=list)


# ─── Phase 1 (issue primitive): issues as persistent entities ────────────────
class IssueOccurrence(BaseModel):
    """One place an issue appears: a region + element on a source page. The same
    issue can have several (nav + hero + footer)."""
    source_page_url: str
    region: str = ""          # nav | hero | body | sidebar | footer
    element_selector: str = ""
    severity: str = "low"     # high | med | low


class IssueRecord(BaseModel):
    """A persistent problem on a site, identified across scans by its
    fingerprint. Scans reconcile this — they never re-create it.

    The pure reconciliation in issues.py builds and compares these; the DB layer
    maps them to the issues / issue_occurrences rows. `id` is set only for issues
    already loaded from the database."""
    id: Optional[str] = None
    fingerprint: str
    status: str = "open"          # open | fixed | ignored
    issue_type: str = "broken"    # broken | dead_cta | unverifiable | redirect
    target_url: str
    source_page_url: str
    anchor_text: str = ""
    region: str = ""              # primary (highest-severity) region
    builder: str = ""
    occurrence_count: int = 1
    monthly_pageviews: Optional[int] = None
    occurrences: list[IssueOccurrence] = Field(default_factory=list)
    # Age survives scan-row deletion; carried forward, never reset on recurrence.
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    fixed_at: Optional[str] = None
    ignored_at: Optional[str] = None


class IssueDiff(BaseModel):
    """What one scan did to a site's issue set. Consumed by the verification
    banner: "You fixed 2 of 4 since {date}".

    `has_baseline` is False on a site's first scan — nothing pre-existing is
    reported as new.
    """
    has_baseline: bool = False
    new: list[IssueRecord] = Field(default_factory=list)
    still_open: list[IssueRecord] = Field(default_factory=list)
    fixed: list[IssueRecord] = Field(default_factory=list)
    ignored_still_present: list[IssueRecord] = Field(default_factory=list)
