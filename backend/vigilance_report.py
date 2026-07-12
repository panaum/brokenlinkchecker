"""Vigilance report — the monthly proof-of-work artifact.

Pure computation: given a site's scans and findings over a period, produce the
report data (verdict, vigilance strip, caught-&-fixed timeline, trend). No I/O,
so it's trivially testable and honest — every number traces to input data.

Honest-numbers rule: dollar/ROI figures appear ONLY when economics data is
supplied; otherwise the ROI line is omitted (never invented).
"""
from datetime import datetime, timezone

DAY = 86400


def _dt(v):
    """Parse an ISO timestamp (tolerant of 'Z' and naive strings) to aware UTC."""
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    s = str(v).replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _get(o, k, default=None):
    return o.get(k, default) if isinstance(o, dict) else getattr(o, k, default)


def _in_period(v, start, end):
    d = _dt(v)
    return bool(d and start <= d <= end)


def _month_label(start):
    return start.strftime("%B %Y")


def compute_report(scans, findings, period_start, period_end,
                   forms_audited=0, integrations_watched=0, economics=None, ads=None):
    """Return the report payload. `scans` and `findings` are dicts/objects with the
    stored fields; `period_start/end` are aware datetimes.

    economics (optional): {plan_monthly_usd, value_per_incident_usd} — enables the
    per-incident ROI line. Absent -> no ROI line (honest).
    """
    start, end = period_start, period_end

    # ── scans in window, oldest -> newest ──
    period_scans = sorted(
        [s for s in (scans or []) if _in_period(_get(s, "scanned_at"), start, end)],
        key=lambda s: _dt(_get(s, "scanned_at")) or start,
    )
    checks_run = len(period_scans)
    latest = period_scans[-1] if period_scans else None
    first = period_scans[0] if period_scans else None

    score = int(_get(latest, "health_score") or 0) if latest else None
    score_start = int(_get(first, "health_score") or 0) if first else None
    score_delta = (score - score_start) if (score is not None and score_start is not None) else 0
    links_verified = int(_get(latest, "total_links") or 0) if latest else 0

    trend = [
        {"date": (_dt(_get(s, "scanned_at")) or start).isoformat(),
         "score": int(_get(s, "health_score") or 0)}
        for s in period_scans
    ]

    # ── caught & fixed timeline from findings ──
    incidents = []
    caught_count = 0
    fixed_count = 0
    for f in (findings or []):
        first_seen = _get(f, "first_seen_at")
        resolved = _get(f, "resolved_at")
        status = _get(f, "status")
        caught_here = _in_period(first_seen, start, end)
        fixed_here = _in_period(resolved, start, end)
        if not (caught_here or fixed_here):
            continue
        if caught_here:
            caught_count += 1
        if fixed_here:
            fixed_count += 1
        verified = status in ("verified_fixed", "resolved") or bool(resolved)
        item = {
            "found_at": _dt(first_seen).isoformat() if _dt(first_seen) else None,
            "fixed_at": _dt(resolved).isoformat() if _dt(resolved) else None,
            "verified": verified,
            "bucket": _get(f, "bucket") or "broken",
            "what": _get(f, "reason") or _human_bucket(_get(f, "bucket")),
            "where": _get(f, "zone") or _get(f, "anchor_text") or "",
            "url": _get(f, "url") or "",
        }
        # Time-to-fix, when both ends are known.
        fs, rs = _dt(first_seen), _dt(resolved)
        if fs and rs and rs >= fs:
            item["hours_to_fix"] = round((rs - fs).total_seconds() / 3600)
        # ROI line — only if economics permits (honest).
        if economics and economics.get("value_per_incident_usd") and economics.get("plan_monthly_usd"):
            mult = economics["value_per_incident_usd"] / economics["plan_monthly_usd"]
            if mult >= 0.5:
                item["roi_line"] = f"this catch ≈ {mult:.1f}× your monthly plan"
        incidents.append(item)

    incidents.sort(key=lambda i: i["found_at"] or "", reverse=True)

    # ── clean streak: days since the most recent NEW issue anywhere ──
    all_first_seen = [_dt(_get(f, "first_seen_at")) for f in (findings or [])]
    all_first_seen = [d for d in all_first_seen if d]
    if all_first_seen:
        last_issue = max(all_first_seen)
        streak_days = max(0, int((end - last_issue).total_seconds() // DAY))
    else:
        streak_days = max(0, int((end - start).total_seconds() // DAY)) if checks_run else 0

    all_clear = caught_count == 0 and (
        not latest or (int(_get(latest, "broken_count") or 0) + int(_get(latest, "dead_cta_count") or 0)) == 0
    )

    month = _month_label(start)
    verdict = _verdict(all_clear, caught_count, fixed_count, month, incidents)

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat(), "label": month},
        "all_clear": all_clear,
        "verdict": verdict,
        "score": score,
        "score_delta": score_delta,
        "streak_days": streak_days,
        "vigilance": {
            "checks_run": checks_run,
            "links_verified": links_verified,
            "forms_audited": int(forms_audited or 0),
            "integrations_watched": int(integrations_watched or 0),
        },
        "caught_count": caught_count,
        "fixed_count": fixed_count,
        "incidents": incidents,
        "trend": trend,
        "uptime_pct": None,  # wired in Wave 3
        "ads": ads,          # {destinations_verified, incidents, has_cost, spend_at_risk} or None
    }


def _human_bucket(bucket):
    return {"broken": "A broken link", "dead_cta": "A dead call-to-action",
            "unverifiable": "An unverifiable link"}.get(bucket, "An issue")


def _verdict(all_clear, caught, fixed, month, incidents):
    if all_clear or caught == 0:
        return f"Everything we watch stayed healthy in {month}."
    # Fastest fix, for the timing clause.
    fixes = [i["hours_to_fix"] for i in incidents if i.get("hours_to_fix") is not None]
    if fixed >= caught and fixes:
        within = max(fixes)
        clause = "within 48 hours" if within <= 48 else f"within {round(within / 24)} days"
        n = f"{caught} issue" + ("s" if caught != 1 else "")
        return f"We caught {n} in {month} — all fixed {clause}."
    n = f"{caught} issue" + ("s" if caught != 1 else "")
    tail = f", {fixed} already fixed" if fixed else ""
    return f"We caught {n} in {month}{tail}."
