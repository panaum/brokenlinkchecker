"""Performance regression detection — deterministic thresholds, honest language."""
from perf_ledger import (percentile, aggregate_scan, detect_regressions,
                         correlate_suspects, suspect_language, build_verdict, cost_index,
                         MIN_SCANS_FOR_TREND)


def _series(vals, start_day=1):
    return [{"scanned_at": f"2026-05-{start_day + i:02d}T06:00:00Z", "p50": v} for i, v in enumerate(vals)]


# ── percentiles / aggregation ──
def test_percentile_and_aggregate():
    assert percentile([100, 200, 300], 50) == 200
    a = aggregate_scan([{"response_ms": 100}, {"response_ms": 300}, {"response_ms": 0}, {"response_ms": 200}])
    assert a["n"] == 3 and a["p50"] == 200


def test_aggregate_ignores_unmeasured():
    assert aggregate_scan([{"response_ms": 0}, {"response_ms": 0}])["n"] == 0


# ── step vs creep vs noise ──
def test_a_clean_step_is_detected():
    # flat ~200, then a sustained jump to ~420 (>25% and >150ms) for 4 scans
    s = _series([200, 210, 195, 205, 420, 430, 415, 425])
    regs = detect_regressions(s)
    assert len(regs) == 1
    assert regs[0]["delta_ms"] >= 150 and regs[0]["ongoing"] is True


def test_slow_creep_does_not_trigger():
    # gradual +10ms/scan — the trailing baseline rises with it, never clears the gate
    s = _series([200, 212, 225, 238, 252, 267, 283, 300, 318])
    assert detect_regressions(s) == []


def test_noisy_flat_stays_quiet():
    # jitter around 200 with a single spike (not sustained ≥3) → no regression
    s = _series([190, 215, 195, 400, 205, 188, 210, 199])
    assert detect_regressions(s) == []


def test_recovery_closes_the_window():
    # step up for 3 scans then back to baseline → window is not ongoing, has recovered_at
    s = _series([200, 200, 200, 420, 430, 420, 205, 200, 198])
    regs = detect_regressions(s)
    assert len(regs) == 1 and regs[0]["ongoing"] is False
    assert regs[0]["recovered_at"] is not None


# ── suspect correlation + language ──
def test_single_suspect_is_likely():
    s = correlate_suspects({"integrations": {"Intercom"}}, {"integrations": {"Intercom", "Calendly"}})
    assert len(s) == 1 and s[0]["kind"] == "integration_added"
    assert suspect_language(s)["confidence"] == "likely"


def test_multiple_suspects_no_favorite():
    s = correlate_suspects(
        {"integrations": set(), "resource_count": 10, "redirect_hops": 0},
        {"integrations": {"Drift"}, "resource_count": 20, "redirect_hops": 1})
    assert len(s) == 3
    lang = suspect_language(s)
    assert lang["confidence"] == "multiple" and "one of several" in lang["text"]


def test_zero_suspects_says_so():
    assert suspect_language(correlate_suspects({}, {}))["confidence"] == "none"


# ── verdict language, incl. thin history ──
def test_thin_history_is_collecting_baseline():
    v = build_verdict(_series([200, 210, 205]), [])
    assert v["collecting"] is True and v["have"] == 3 and v["need"] == MIN_SCANS_FOR_TREND


def test_verdict_slower_since_when_ongoing():
    s = _series([200, 200, 200, 420, 430, 420, 425])
    v = build_verdict(s, detect_regressions(s))
    assert v["state"] == "slower" and "slower since" in v["text"]


def test_verdict_stable_and_faster():
    assert build_verdict(_series([200, 205, 198, 202, 200, 199]), [])["state"] == "stable"
    faster = build_verdict(_series([500, 480, 300, 260, 240, 230]), [])
    assert faster["state"] == "faster"


# ── cost index ──
def test_cost_index_medians_and_ranks():
    idx = cost_index({"intercom.io": [280, 300, 290], "calendly.com": [120, 100]})
    assert idx[0]["host"] == "intercom.io" and idx[0]["sites"] == 3 and idx[0]["median_added_ms"] == 290
    assert idx[1]["host"] == "calendly.com"
