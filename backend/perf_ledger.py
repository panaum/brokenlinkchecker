"""Performance Regression Ledger — pure, deterministic.

"When did it get slow, and what did it." Reads EXISTING per-link response_ms
across historical scans as a time-series, finds sustained regressions, and — by
joining the integrations/resource timeline — lists what CHANGED in the window.
Never asserts causation: it lists suspects and labels its confidence.

All thresholds live here, documented, in ONE place.
"""
from statistics import median

# ── The only tuning constants. A regression must clear BOTH gates and sustain. ──
REGRESSION_PCT = 0.25      # +25% over baseline …
REGRESSION_MS = 150        # … AND +150ms absolute (filters noise on fast pages)
SUSTAIN_SCANS = 3          # … for at least this many consecutive scans
BASELINE_K = 3             # baseline = median of this many scans before the step
MIN_SCANS_FOR_TREND = 5    # fewer than this → "collecting baseline", no verdict


def _get(o, k, d=None):
    return o.get(k, d) if isinstance(o, dict) else getattr(o, k, d)


def percentile(values, p):
    """Nearest-rank percentile of a numeric list. None if empty."""
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    rank = max(0, min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1)))))
    return xs[rank]


def aggregate_scan(results):
    """p50/p90 of the real (measured, >0) response_ms in one scan's results."""
    ms = [int(_get(r, "response_ms") or 0) for r in (results or [])]
    ms = [m for m in ms if m and m > 0]
    if not ms:
        return {"p50": None, "p90": None, "n": 0}
    return {"p50": percentile(ms, 50), "p90": percentile(ms, 90), "n": len(ms)}


def detect_regressions(series):
    """`series`: [{scanned_at, p50, ...}] oldest→newest. Returns regression
    windows. A step is distinguished from slow creep because the baseline is the
    median of the scans *before* the step — creep raises the baseline with it and
    never clears the gate; a step leaves the baseline low."""
    pts = [p for p in (series or []) if _get(p, "p50") is not None]
    n = len(pts)
    regs = []
    i = BASELINE_K
    while i < n:
        baseline = median(_get(pts[k], "p50") for k in range(i - BASELINE_K, i))

        def elevated(idx):
            v = _get(pts[idx], "p50")
            return v >= baseline * (1 + REGRESSION_PCT) and v >= baseline + REGRESSION_MS

        if baseline > 0 and elevated(i):
            j = i
            while j < n and elevated(j):
                j += 1
            if (j - i) >= SUSTAIN_SCANS:
                peak = max(_get(pts[k], "p50") for k in range(i, j))
                regs.append({
                    "start_at": _get(pts[i], "scanned_at"),
                    "end_at": _get(pts[j - 1], "scanned_at"),
                    "recovered_at": _get(pts[j], "scanned_at") if j < n else None,
                    "baseline_p50": round(baseline),
                    "peak_p50": peak,
                    "delta_ms": round(peak - baseline),
                    "delta_pct": round((peak - baseline) / baseline * 100),
                    "ongoing": j >= n,
                })
                i = j
                continue
        i += 1
    return regs


# ── Suspect correlation — what CHANGED in the regression window ──────────────
def correlate_suspects(before, after):
    """before/after: {integrations:set[str host or category], resource_count:int,
    resource_types:set[str], redirect_hops:int}. Returns a list of suspect
    dicts — each a factual change, never a claim of cause."""
    before, after = before or {}, after or {}
    suspects = []
    bi, ai = set(before.get("integrations") or []), set(after.get("integrations") or [])
    for added in sorted(ai - bi):
        suspects.append({"kind": "integration_added", "what": added,
                         "detail": f"{added} added"})
    for removed in sorted(bi - ai):
        suspects.append({"kind": "integration_removed", "what": removed,
                         "detail": f"{removed} removed"})
    bc, ac = before.get("resource_count") or 0, after.get("resource_count") or 0
    if ac - bc >= 5:
        suspects.append({"kind": "resources_added", "what": f"+{ac - bc} resources",
                         "detail": f"{ac - bc} more resources on the page"})
    bh, ah = before.get("redirect_hops") or 0, after.get("redirect_hops") or 0
    if ah > bh:
        suspects.append({"kind": "redirect_added", "what": f"+{ah - bh} redirect hop(s)",
                         "detail": f"{ah - bh} more redirect hop(s)"})
    return suspects


def suspect_language(suspects):
    """Honesty-labeled phrasing. One → 'likely'; many → all listed, no favorite;
    none → explicit 'no recorded change'."""
    if not suspects:
        return {"confidence": "none", "text": "no recorded change in this window"}
    if len(suspects) == 1:
        return {"confidence": "likely", "text": f"likely {suspects[0]['detail']}"}
    joined = "; ".join(s["detail"] for s in suspects)
    return {"confidence": "multiple", "text": f"one of several changes — {joined}"}


def build_verdict(series, regressions):
    """The one-sentence verdict. Handles thin history honestly."""
    pts = [p for p in (series or []) if _get(p, "p50") is not None]
    if len(pts) < MIN_SCANS_FOR_TREND:
        return {"state": "baseline", "text": f"Collecting baseline ({len(pts)}/{MIN_SCANS_FOR_TREND} scans).",
                "collecting": True, "have": len(pts), "need": MIN_SCANS_FOR_TREND}
    ongoing = [r for r in regressions if r.get("ongoing")]
    if ongoing:
        r = max(ongoing, key=lambda x: x["delta_ms"])
        secs = r["delta_ms"] / 1000.0
        return {"state": "slower", "text": f"{secs:.1f}s slower since {_short(r['start_at'])}.",
                "regression": r}
    first, last = _get(pts[0], "p50"), _get(pts[-1], "p50")
    if first and last < first * 0.8:
        return {"state": "faster", "text": f"{(first - last) / 1000.0:.1f}s faster than when monitoring began."}
    return {"state": "stable", "text": "Load time is stable — no sustained regression."}


def _short(iso):
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).strftime("%b %-d")
    except Exception:
        try:
            return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).strftime("%b %d")
        except Exception:
            return str(iso)[:10]


# ── Third-party cost index — needs the multi-site vantage ───────────────────
def cost_index(observations):
    """observations: {host: [added_latency_ms, ...]} — one delta per site where
    the host is present (page-with vs comparable page-without). Returns per-host
    median added latency + site count. Observational; the UI states the method."""
    out = []
    for host, deltas in (observations or {}).items():
        ds = [d for d in deltas if d is not None]
        if not ds:
            continue
        out.append({"host": host, "sites": len(ds), "median_added_ms": round(median(ds))})
    out.sort(key=lambda x: -x["median_added_ms"])
    return out
