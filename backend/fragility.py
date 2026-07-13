"""Fragility & Decay Score — longitudinal read of findings history.

"Which sites break, how often, and where." Pure + deterministic. THE FACTORS
RULE IS ABSOLUTE: fragility_score() always returns the contributing factors with
the number — a score without reasons is astrology.

Perturbation-stable by design: every driver is capped and weighted so a single
extra finding nudges the score a few points, never jumps a band.
"""
from datetime import datetime, timezone
from statistics import median

# ── History gate: below this we show "insufficient history", never a score. ──
MIN_DAYS = 60
MIN_SCANS = 8

# ── Score weights (sum 100), documented. Each driver normalized to 0..1. ──
W_RATE = 35        # breakage frequency (new breakages / 90d)
W_RECUR = 20       # recurrence (fixes that don't hold)
W_MTTR = 20        # how long breakages linger
W_FUNNEL = 15      # concentration in funnel zones (CTA/nav) — worse
W_SPREAD = 10      # how many distinct pages break

RATE_CAP = 6.0     # ≥6 new breakages/90d saturates the rate driver
MTTR_CAP = 14.0    # ≥14-day median fix saturates the mttr driver
WINDOW_DAYS = 90

_FUNNEL_ZONES = ("cta", "nav", "header", "hero", "button", "menu", "footer-cta")


def _dt(v):
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _now(now=None):
    return now or datetime.now(timezone.utc)


def dedupe_events(finding_rows):
    """Finding rows repeat per-snapshot; collapse to distinct breakage events by
    (fingerprint, first-seen day). Each event = the earliest first_seen for that
    occurrence + its resolved_at + zone."""
    seen = {}
    for r in finding_rows or []:
        fp = r.get("fingerprint") or r.get("url") or ""
        fs = _dt(r.get("first_seen_at"))
        if not fp or not fs:
            continue
        key = (fp, fs.date())
        rs = _dt(r.get("resolved_at"))
        if key not in seen:
            seen[key] = {"fingerprint": fp, "first_seen": fs, "resolved": rs,
                         "zone": (r.get("zone") or "").lower(), "url": r.get("url") or ""}
        else:
            # keep the resolution if any row has it
            if rs and not seen[key]["resolved"]:
                seen[key]["resolved"] = rs
    return sorted(seen.values(), key=lambda e: e["first_seen"])


def history_gate(monitoring_days, scan_count):
    if monitoring_days is None or monitoring_days < MIN_DAYS or (scan_count or 0) < MIN_SCANS:
        return {"sufficient": False, "reason": f"Needs {MIN_DAYS}+ days and {MIN_SCANS}+ scans of history.",
                "have_days": monitoring_days, "have_scans": scan_count}
    return {"sufficient": True}


def compute_metrics(events, now=None, window_days=WINDOW_DAYS):
    now = _now(now)
    cutoff = now.timestamp() - window_days * 86400
    recent = [e for e in events if e["first_seen"].timestamp() >= cutoff]

    new_per_window = len(recent)
    new_per_month = round(new_per_window / (window_days / 30.0), 2)

    # mean time-to-resolution (resolved events only)
    ttrs = [(e["resolved"] - e["first_seen"]).total_seconds() / 86400
            for e in events if e.get("resolved") and e["resolved"] >= e["first_seen"]]
    mttr_days = round(median(ttrs), 1) if ttrs else None

    # mean time-between-breakages (across all events, chronological)
    times = sorted(e["first_seen"].timestamp() for e in events)
    gaps = [(b - a) / 86400 for a, b in zip(times, times[1:])]
    mtbb_days = round(median(gaps), 1) if gaps else None

    # recurrence: fraction of fingerprints that broke more than once
    from collections import Counter
    fp_counts = Counter(e["fingerprint"] for e in events)
    recurring = [fp for fp, n in fp_counts.items() if n > 1]
    recurrence_rate = round(len(recurring) / len(fp_counts), 2) if fp_counts else 0.0

    # zone concentration (of recent breakages) + funnel share
    funnel = sum(1 for e in recent if any(z in e["zone"] for z in _FUNNEL_ZONES))
    funnel_share = round(funnel / new_per_window, 2) if new_per_window else 0.0
    distinct_pages = len({e["url"] for e in recent})

    return {"new_per_month": new_per_month, "new_per_window": new_per_window,
            "mttr_days": mttr_days, "mtbb_days": mtbb_days,
            "recurrence_rate": recurrence_rate, "recurring_fingerprints": recurring,
            "funnel_share": funnel_share, "distinct_pages": distinct_pages}


def _clamp(x):
    return max(0.0, min(1.0, x))


def fragility_score(metrics):
    """0..100 + band + the factors that produced it (always)."""
    m = metrics
    rate_n = _clamp(m["new_per_window"] / RATE_CAP)
    recur_n = _clamp(m["recurrence_rate"])
    mttr_n = _clamp((m["mttr_days"] or 0) / MTTR_CAP)
    funnel_n = _clamp(m["funnel_share"])
    spread_n = _clamp(m["distinct_pages"] / 5.0)

    score = round(W_RATE * rate_n + W_RECUR * recur_n + W_MTTR * mttr_n +
                  W_FUNNEL * funnel_n + W_SPREAD * spread_n)
    band = "sturdy" if score <= 25 else ("brittle" if score >= 60 else "normal")

    factors = []
    if m["new_per_window"]:
        factors.append(f"{m['new_per_window']} breakage{'s' if m['new_per_window'] != 1 else ''} in {WINDOW_DAYS} days")
    if m["funnel_share"] >= 0.6 and m["new_per_window"]:
        factors.append("mostly in funnel pages" if m["funnel_share"] < 1 else "all in funnel pages")
    if m["mttr_days"] is not None:
        factors.append(f"median fix {m['mttr_days']:g} day{'s' if m['mttr_days'] != 1 else ''}")
    if m["recurrence_rate"] >= 0.25:
        factors.append(f"{int(m['recurrence_rate'] * 100)}% of issues recurred")
    if not factors:
        factors.append("no breakages in the window")
    return {"score": score, "band": band, "factors": factors}


def recurrence_clusters(events):
    """Fingerprints that broke ≥2 times — the fixes that aren't holding."""
    from collections import defaultdict
    by_fp = defaultdict(list)
    for e in events:
        by_fp[e["fingerprint"]].append(e)
    out = []
    for fp, evs in by_fp.items():
        if len(evs) >= 2:
            evs.sort(key=lambda x: x["first_seen"])
            out.append({"fingerprint": fp, "url": evs[0]["url"], "zone": evs[0]["zone"],
                        "count": len(evs), "first": evs[0]["first_seen"].isoformat(),
                        "last": evs[-1]["first_seen"].isoformat()})
    out.sort(key=lambda x: -x["count"])
    return out


def sibling_template(sites_events):
    """Cross-site pattern within a client: the same zone breaking on multiple
    sites suggests a shared-template root cause. sites_events: {site_id: events}."""
    from collections import defaultdict
    zone_sites = defaultdict(set)
    for sid, evs in (sites_events or {}).items():
        for e in evs:
            if e["zone"]:
                zone_sites[e["zone"]].add(sid)
    return [{"zone": z, "sites": sorted(s)} for z, s in zone_sites.items() if len(s) >= 3]


def score_trend(events, monitoring_start, now=None, points=6):
    """Fragility score computed at evenly-spaced points since monitoring began —
    'fragility 61 → 34' is the retainer's value in one line."""
    now = _now(now)
    start = _dt(monitoring_start) or (events[0]["first_seen"] if events else now)
    span = (now - start).total_seconds()
    if span <= 0:
        return []
    series = []
    for i in range(1, points + 1):
        at = datetime.fromtimestamp(start.timestamp() + span * i / points, tz=timezone.utc)
        window_events = [e for e in events if e["first_seen"] <= at]
        series.append({"at": at.isoformat(),
                       "score": fragility_score(compute_metrics(window_events, now=at))["score"]})
    return series


def allocation_suggestion(band, quiet_days, current_freq):
    """Suggest — never auto-apply. Every suggestion carries its evidence."""
    if band == "brittle":
        return {"suggest_freq": "daily", "current": current_freq,
                "text": "Brittle site — consider daily monitoring.",
                "evidence": "It breaks often enough that a weekly cadence can miss issues for days."}
    if band == "sturdy" and (quiet_days or 0) >= 45 and current_freq == "daily":
        return {"suggest_freq": "weekly", "current": current_freq,
                "text": "Sturdy and quiet — weekly is likely sufficient.",
                "evidence": f"No breakages in {quiet_days} days."}
    return None
