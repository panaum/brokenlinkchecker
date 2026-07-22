"""
Issues as the primitive.

An issue is a persistent entity on a site — detected once, then carried across
scans until it is fixed or ignored. A scan is an observation that reconciles the
issue set: it can open a new issue, keep an open one alive, mark a vanished one
fixed, or re-touch an ignored one.

Everything hangs off the fingerprint. If two scans of an unchanged page produce
different fingerprints, issues look new forever and nothing is ever reported as
fixed. So identity reuses the same battle-tested normalization as diffing.py —
there is exactly one URL-normalizer in this codebase, on purpose.

Pure functions only: no DB, no clock. Callers pass `now` so tests are
deterministic and the same logic drives both the live scan path and the
historical backfill.

── One deviation from the Phase 1 prompt, flagged for review ──────────────────
The prompt specifies the fingerprint as
    normalize(target_url) + normalize(source_page_url) + region.
Including `region` in identity would split one broken target across regions into
several issues — but the design reference shows a single "/book-now" issue whose
detail lists occurrences in Nav, Hero AND Footer. Region-in-identity contradicts
that reference (and the existing findings model, where a nav+footer link is one
finding with two zones). So identity here is (target_url, source_page_url) and
`region` lives on issue_occurrences. One target -> one issue -> many regions.
If you'd rather have region in identity, it's a one-line change in
`issue_fingerprint` + the migration comment — say the word.
"""
import hashlib

from diffing import normalize_url
from models import IssueOccurrence, IssueRecord, IssueDiff


# ─── Taxonomy mapping ────────────────────────────────────────────────────────
_ISSUE_TYPES = frozenset({"broken", "dead_cta", "unverifiable", "redirect"})

# Free-form scan zones/categories -> the five canonical regions. Matched by
# substring, lowercased, so "Body text" and "Primary navigation" both land.
_REGION_RULES = (
    ("nav", "nav"),
    ("menu", "nav"),
    ("hero", "hero"),
    ("header", "hero"),
    ("cta", "hero"),
    ("banner", "hero"),
    ("sidebar", "sidebar"),
    ("aside", "sidebar"),
    ("footer", "footer"),
)
_DEFAULT_REGION = "body"

# Checker priority -> occurrence severity.
_SEVERITY_BY_PRIORITY = {
    "critical": "high",
    "high": "high",
    "medium": "med",
    "low": "low",
}


def map_region(zone: str) -> str:
    """A scan zone/category -> nav | hero | body | sidebar | footer."""
    z = (zone or "").strip().lower()
    if not z:
        return _DEFAULT_REGION
    for needle, region in _REGION_RULES:
        if needle in z:
            return region
    return _DEFAULT_REGION


def map_severity(priority: str) -> str:
    """Checker priority -> high | med | low. Unknown/None -> low."""
    return _SEVERITY_BY_PRIORITY.get((priority or "").strip().lower(), "low")


def map_issue_type(bucket: str) -> str:
    """A finding bucket -> a valid issue_type. Unknown -> unverifiable (never a
    red bucket when unsure — same rule the checker follows)."""
    b = (bucket or "").strip().lower()
    return b if b in _ISSUE_TYPES else "unverifiable"


# ─── Fingerprint ─────────────────────────────────────────────────────────────
def issue_fingerprint(target_url: str, source_page_url: str) -> str:
    """Stable identity for an issue: (target, source page).

    The target keeps its fragment (a broken #team and #pricing are two issues);
    the source page drops its fragment (/p and /p#top are one page). Tracking
    params, host case, default ports and trailing slashes are normalized away by
    normalize_url, so the same problem fingerprints identically every scan.
    """
    parts = "\x1f".join((
        normalize_url(target_url, keep_fragment=True),
        normalize_url(source_page_url, keep_fragment=False),
    ))
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()[:16]


def _get(result, field, default=None):
    if isinstance(result, dict):
        return result.get(field, default)
    return getattr(result, field, default)


_SEVERITY_RANK = {"high": 3, "med": 2, "low": 1}


def build_issues_from_scan(source_page_url: str, results, now: str = None) -> list:
    """Turn one scan's flagged results into IssueRecords with occurrences.

    A working link is not an issue. A target flagged in several zones becomes ONE
    issue with one occurrence per region. Results that fingerprint identically
    (e.g. the same href seen twice) are merged, their occurrences unioned.
    """
    by_fp: dict[str, IssueRecord] = {}

    for r in results:
        bucket = _get(r, "bucket", "ok")
        if bucket in (None, "", "ok"):
            continue

        target = _get(r, "url", "") or ""
        fp = issue_fingerprint(target, source_page_url)

        zones = _get(r, "zones") or []
        if not zones:
            cat = _get(r, "category", "") or ""
            zones = [cat] if cat else [""]
        selector = _get(r, "source_element", "") or ""
        severity = map_severity(_get(r, "priority", "low"))

        occ = [
            IssueOccurrence(
                source_page_url=source_page_url,
                region=map_region(z),
                element_selector=selector,
                severity=severity,
            )
            for z in zones
        ]

        existing = by_fp.get(fp)
        if existing is None:
            by_fp[fp] = IssueRecord(
                fingerprint=fp,
                status="open",
                issue_type=map_issue_type(bucket),
                target_url=target,
                source_page_url=source_page_url,
                anchor_text=_get(r, "anchor_text", "") or "",
                builder=_get(r, "builder", "") or "",
                occurrences=occ,
                first_seen_at=now,
                last_seen_at=now,
            )
        else:
            existing.occurrences.extend(occ)

    # De-dupe occurrences, set primary region (highest severity), count.
    for issue in by_fp.values():
        seen = set()
        deduped = []
        for o in issue.occurrences:
            key = (o.source_page_url, o.region, o.element_selector)
            if key not in seen:
                seen.add(key)
                deduped.append(o)
        deduped.sort(key=lambda o: _SEVERITY_RANK.get(o.severity, 0), reverse=True)
        issue.occurrences = deduped
        issue.occurrence_count = len(deduped)
        issue.region = deduped[0].region if deduped else _DEFAULT_REGION

    return list(by_fp.values())


# ─── Reconciliation ──────────────────────────────────────────────────────────
def reconcile_issues(previous, current, now: str = None) -> IssueDiff:
    """Fold this scan's issues into the site's existing issue set.

    NEW                   — fingerprint the site has never seen
    STILL_OPEN            — an open (or regressed-from-fixed) issue seen again;
                            keeps its original first_seen_at, refreshes occurrences
    FIXED                 — an open issue whose fingerprint is absent this scan
    IGNORED_STILL_PRESENT — an ignored issue seen again: last_seen updated, but it
                            never resurfaces as open (only an explicit reopen does)

    `previous` of None means the site has no baseline (first scan): nothing is
    reported, and has_baseline is False so the UI shows a plain header rather
    than flagging every pre-existing issue as new.

    Not returned, by design: an ignored issue that is *absent* this scan is left
    untouched (still ignored) — "never resurface unless I explicitly reopen"
    applies to disappearance too; and an already-fixed issue that stays gone
    needs no change.
    """
    has_baseline = previous is not None
    prev_by_fp = {i.fingerprint: i for i in (previous or [])}

    new, still_open, ignored_still_present = [], [], []
    current_fps = set()

    for cur in current:
        current_fps.add(cur.fingerprint)
        prior = prev_by_fp.get(cur.fingerprint)

        if prior is None:
            new.append(cur.model_copy(update={
                "status": "open",
                "first_seen_at": cur.first_seen_at or now,
                "last_seen_at": now,
            }))
        elif prior.status == "ignored":
            ignored_still_present.append(prior.model_copy(update={
                "status": "ignored",
                "last_seen_at": now,
                "occurrences": cur.occurrences,
                "occurrence_count": cur.occurrence_count,
                "region": cur.region,
            }))
        else:
            # Open, or previously fixed and now regressed — either way it is open
            # again and keeps the age it was first detected with.
            still_open.append(prior.model_copy(update={
                "status": "open",
                "first_seen_at": prior.first_seen_at or now,
                "last_seen_at": now,
                "fixed_at": None,
                "occurrences": cur.occurrences,
                "occurrence_count": cur.occurrence_count,
                "region": cur.region,
                "issue_type": cur.issue_type,
            }))

    fixed = [
        prior.model_copy(update={"status": "fixed", "fixed_at": now})
        for prior in (previous or [])
        if prior.status == "open" and prior.fingerprint not in current_fps
    ]

    return IssueDiff(
        has_baseline=has_baseline,
        new=new,
        still_open=still_open,
        fixed=fixed,
        ignored_still_present=ignored_still_present,
    )


def summarize_issue_diff(diff: IssueDiff) -> str:
    """'You fixed 2 of N …' lead line for the verification banner."""
    if not diff.has_baseline:
        return "First scan — no baseline to compare against yet"
    open_now = len(diff.new) + len(diff.still_open)
    return (
        f"{len(diff.new)} new · "
        f"{len(diff.fixed)} fixed · "
        f"{open_now} open"
    )
