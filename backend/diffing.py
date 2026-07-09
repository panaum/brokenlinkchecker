"""
Baseline diffing: stable finding identity across scans.

Everything downstream — issue age, "broken for 12 days", fix verification,
client emails — hangs off the fingerprint. If two scans of an unchanged page
produce different fingerprints, every later feature inherits the bug: issues
look new forever, ages reset, and nothing is ever reported as fixed.

Pure functions only. No DB, no clock — callers pass `now` so tests are
deterministic.
"""
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from models import FindingRecord, ScanDiff


# ─── Tracking parameters ─────────────────────────────────────────────────────
# Campaign/click identifiers that change per visit or per channel. Two links
# differing only by these point at the same resource, so they must fingerprint
# identically or every scan reports the whole page as new.
#
# Deliberately conservative: `ref` and `source` are NOT here. They are often
# genuine routing/content parameters, and wrongly stripping them would merge two
# distinct findings into one — a silent under-report, which is worse than a
# duplicate.
_TRACKING_PARAMS = frozenset({
    "gclid", "gbraid", "wbraid", "dclid", "fbclid", "msclkid", "yclid",
    "ttclid", "twclid", "igshid", "epik", "mkt_tok",
    "mc_cid", "mc_eid", "_ga", "_gl", "s_kwcid",
    "oly_enc_id", "oly_anon_id",
})
# Whole families, matched by prefix.
_TRACKING_PREFIXES = ("utm_", "hsa_", "pk_", "piwik_", "matomo_", "vero_")

_DEFAULT_PORTS = {"http": "80", "https": "443"}

_WS_RE = re.compile(r"\s+")


def _is_tracking_param(name: str) -> bool:
    n = name.lower()
    return n in _TRACKING_PARAMS or n.startswith(_TRACKING_PREFIXES)


def normalize_url(url: str, *, keep_fragment: bool = False) -> str:
    """Canonical form of a URL for identity purposes.

    Strips tracking parameters, lowercases scheme/host, drops the default port,
    removes a trailing slash (except on the root), and sorts the remaining query
    parameters so their order cannot change the fingerprint.

    `keep_fragment` matters. For a *page* URL the fragment is noise: /pricing and
    /pricing#top are the same page. For a *target href* the fragment is identity:
    a broken "#team" and a broken "#pricing" on the same page are two different
    findings, and collapsing them would make one of them permanently invisible.
    """
    if not url:
        return ""

    raw = url.strip()
    # Non-HTTP targets (mailto:, tel:, javascript:) have no meaningful URL
    # structure to normalize — lowercase the scheme and keep the rest verbatim.
    if not raw.lower().startswith(("http://", "https://")):
        scheme, sep, rest = raw.partition(":")
        return f"{scheme.lower()}{sep}{rest}" if sep else raw

    parts = urlsplit(raw)

    scheme = parts.scheme.lower()
    host = parts.hostname or ""
    port = parts.port

    netloc = host
    if port and str(port) != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{port}"

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not _is_tracking_param(k)]
    query = urlencode(sorted(kept))

    fragment = parts.fragment if keep_fragment else ""
    return urlunsplit((scheme, netloc, path, query, fragment))


def normalize_anchor_text(text: str) -> str:
    """Collapse whitespace and case. Copy tweaks shouldn't orphan a finding."""
    if not text:
        return ""
    return _WS_RE.sub(" ", text).strip().lower()[:80]


def finding_fingerprint(page_url: str, href: str, anchor_text: str, kind: str) -> str:
    """Stable identity for one finding: (page, target, anchor text, kind).

    The page URL drops its fragment; the href keeps it (see normalize_url).
    """
    parts = "\x1f".join((
        normalize_url(page_url, keep_fragment=False),
        normalize_url(href, keep_fragment=True),
        normalize_anchor_text(anchor_text),
        (kind or "").strip().lower(),
    ))
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()[:16]


def _get(result, field, default=None):
    if isinstance(result, dict):
        return result.get(field, default)
    return getattr(result, field, default)


def fingerprint_result(page_url: str, result) -> str:
    return finding_fingerprint(
        page_url,
        _get(result, "url", "") or "",
        _get(result, "anchor_text", "") or "",
        _get(result, "link_kind", "http") or "http",
    )


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def link_fingerprints(page_url: str, results) -> list:
    """Every scanned link, working or not — backs the 'New Links' card."""
    seen, out = set(), []
    for r in results:
        fp = fingerprint_result(page_url, r)
        if fp not in seen:
            seen.add(fp)
            out.append(fp)
    return out


def collect_findings(page_url: str, results, now: str = None) -> list:
    """Flagged rows only. A working link is not a finding."""
    now = now or utcnow_iso()
    findings, seen = [], set()
    for r in results:
        bucket = _get(r, "bucket", "ok")
        if bucket in (None, "ok"):
            continue
        fp = fingerprint_result(page_url, r)
        if fp in seen:
            continue
        seen.add(fp)
        zones = _get(r, "zones") or []
        findings.append(FindingRecord(
            fingerprint=fp,
            bucket=bucket,
            confidence=_get(r, "confidence", "high") or "high",
            url=_get(r, "url", "") or "",
            anchor_text=_get(r, "anchor_text", "") or "",
            zone=(zones[0] if zones else _get(r, "category", "") or ""),
            reason=_get(r, "reason", "") or _get(r, "error", "") or "",
            first_seen_at=now,
            resolved_at=None,
            status="open",
        ))
    return findings


def diff_findings(previous, current, now: str = None) -> ScanDiff:
    """Compare two snapshots' findings.

    NEW       — fingerprint absent from the previous snapshot
    RECURRING — present in both; carries its original first_seen_at forward
    FIXED     — present previously, gone now; stamped resolved_at

    `previous` of None means there is no baseline: the caller renders "n/a"
    rather than claiming everything is new.
    """
    now = now or utcnow_iso()
    prev_by_fp = {f.fingerprint: f for f in (previous or [])}

    new, recurring = [], []
    for f in current:
        prior = prev_by_fp.get(f.fingerprint)
        if prior is None:
            new.append(f.model_copy(update={"first_seen_at": f.first_seen_at or now}))
        else:
            # Age is measured from the first time we ever saw it.
            recurring.append(f.model_copy(update={
                "first_seen_at": prior.first_seen_at,
                "status": "open",
            }))

    current_fps = {f.fingerprint for f in current}
    fixed = [
        f.model_copy(update={"resolved_at": now, "status": "resolved"})
        for f in (previous or [])
        if f.fingerprint not in current_fps
    ]

    return ScanDiff(
        has_baseline=previous is not None,
        new=new,
        recurring=recurring,
        fixed=fixed,
    )


def diff_link_counts(previous_fps, current_fps) -> dict:
    """'New Links' card: links present now that were not there last time."""
    if previous_fps is None:
        return {"has_baseline": False, "new_links": None, "removed_links": None}
    prev, curr = set(previous_fps), set(current_fps)
    return {
        "has_baseline": True,
        "new_links": len(curr - prev),
        "removed_links": len(prev - curr),
    }


def _parse_iso(value: str):
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def issue_age_days(first_seen_at: str, now: str = None) -> int:
    """Whole days since a finding was first observed. 0 when unknown."""
    first = _parse_iso(first_seen_at)
    if first is None:
        return 0
    current = _parse_iso(now) or datetime.now(timezone.utc)
    return max(0, (current - first).days)


def age_phrase(finding: FindingRecord, now: str = None) -> str:
    """'broken for 12 days' — the line every report and email leads with."""
    days = issue_age_days(finding.first_seen_at, now)
    noun = "Broken" if finding.bucket == "broken" else "Open"
    if days == 0:
        return f"{noun} since today"
    if days == 1:
        return f"{noun} for 1 day"
    return f"{noun} for {days} days"


def summarize_diff(diff: ScanDiff) -> str:
    """'N new · M fixed · K still open' — the lead line for reports and emails."""
    if not diff.has_baseline:
        return "First scan — no baseline to compare against yet"
    return (
        f"{len(diff.new)} new · "
        f"{len(diff.fixed)} fixed · "
        f"{len(diff.recurring)} still open"
    )


def diff_status_by_fingerprint(diff: ScanDiff) -> dict:
    """fingerprint -> 'new' | 'recurring', for annotating scan results."""
    status = {f.fingerprint: "new" for f in diff.new}
    status.update({f.fingerprint: "recurring" for f in diff.recurring})
    return status
