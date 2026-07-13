"""Fragility & Decay — metric math, score stability, the factors rule."""
from datetime import datetime, timezone, timedelta

from fragility import (dedupe_events, history_gate, compute_metrics, fragility_score,
                       recurrence_clusters, sibling_template, allocation_suggestion,
                       score_trend, MIN_DAYS, MIN_SCANS)

NOW = datetime(2026, 7, 13, tzinfo=timezone.utc)


def _row(fp, days_ago_seen, days_ago_resolved=None, zone="body", url=None):
    fs = (NOW - timedelta(days=days_ago_seen)).isoformat()
    rs = (NOW - timedelta(days=days_ago_resolved)).isoformat() if days_ago_resolved is not None else None
    return {"fingerprint": fp, "zone": zone, "url": url or f"https://x.com/{fp}",
            "first_seen_at": fs, "resolved_at": rs, "status": "resolved" if rs else "open"}


# ── dedupe: per-snapshot repeats collapse to one event ──
def test_dedupe_collapses_snapshot_repeats():
    rows = [_row("a", 10), _row("a", 10), _row("a", 10, days_ago_resolved=8)]
    ev = dedupe_events(rows)
    assert len(ev) == 1 and ev[0]["resolved"] is not None


# ── history gate ──
def test_history_gate_blocks_thin_history():
    assert history_gate(30, 20)["sufficient"] is False        # too few days
    assert history_gate(90, 4)["sufficient"] is False         # too few scans
    assert history_gate(MIN_DAYS, MIN_SCANS)["sufficient"] is True


# ── metric math across history shapes ──
def test_steady_low_history_is_sturdy():
    ev = dedupe_events([_row("a", 80, 78), _row("b", 40, 39)])  # 2 old, resolved fast, body
    m = compute_metrics(ev, now=NOW)
    s = fragility_score(m)
    assert s["band"] == "sturdy" and s["score"] <= 25


def test_frequent_funnel_breakage_is_brittle_with_factors():
    rows = [_row(f"f{i}", d, zone="cta") for i, d in enumerate([5, 15, 25, 40, 55, 70])]
    m = compute_metrics(dedupe_events(rows), now=NOW)
    s = fragility_score(m)
    assert s["band"] == "brittle" and s["score"] >= 60
    # THE FACTORS RULE — never a score without reasons
    assert any("breakage" in f for f in s["factors"])
    assert any("funnel" in f for f in s["factors"])


def test_recurrence_and_mttr_feed_the_score():
    rows = [_row("a", 80, 40), _row("a", 30, 5), _row("a", 10)]  # same fp broke 3x, slow fixes
    ev = dedupe_events(rows)
    m = compute_metrics(ev, now=NOW)
    assert m["recurrence_rate"] == 1.0 and m["mttr_days"] is not None
    clusters = recurrence_clusters(ev)
    assert clusters and clusters[0]["count"] == 3


# ── score stability (perturbation) ──
def test_one_extra_finding_does_not_jump_a_band():
    # a site solidly mid-band (normal); adding one finding must keep it there
    base = [_row("a", 20, 18, zone="cta"), _row("b", 50, 48, zone="body"), _row("c", 80, 78, zone="body")]
    ev = dedupe_events(base)
    s1 = fragility_score(compute_metrics(ev, now=NOW))
    assert s1["band"] == "normal"
    ev2 = dedupe_events(base + [_row("d", 12, 10, zone="body")])
    s2 = fragility_score(compute_metrics(ev2, now=NOW))
    assert s1["band"] == s2["band"]                 # no band jump from one finding
    assert abs(s1["score"] - s2["score"]) <= 12     # gentle, bounded move


# ── improvement trend ──
def test_score_trend_improves_when_breakages_stop():
    # heavy breakage early, quiet lately → later-window score should be <= early
    rows = [_row(f"e{i}", d, days_ago_resolved=d - 2, zone="cta") for i, d in enumerate([170, 165, 160, 155, 150])]
    ev = dedupe_events(rows)
    trend = score_trend(ev, monitoring_start=(NOW - timedelta(days=180)).isoformat(), now=NOW, points=4)
    assert trend[0]["score"] >= trend[-1]["score"]


# ── cross-site sibling template ──
def test_sibling_template_needs_three_sites():
    ev = {"s1": dedupe_events([_row("a", 5, zone="footer")]),
          "s2": dedupe_events([_row("b", 5, zone="footer")]),
          "s3": dedupe_events([_row("c", 5, zone="footer")])}
    sib = sibling_template(ev)
    assert sib and sib[0]["zone"] == "footer" and len(sib[0]["sites"]) == 3
    # only two sites → not a pattern
    assert sibling_template({"s1": ev["s1"], "s2": ev["s2"]}) == []


# ── allocation suggestions (suggest, never apply) ──
def test_allocation_suggestions_with_evidence():
    brittle = allocation_suggestion("brittle", 0, "weekly")
    assert brittle["suggest_freq"] == "daily" and brittle["evidence"]
    quiet = allocation_suggestion("sturdy", 60, "daily")
    assert quiet["suggest_freq"] == "weekly"
    assert allocation_suggestion("normal", 10, "weekly") is None
