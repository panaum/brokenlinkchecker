"""Inbound-404 triage — parse both formats, normalize, rank measured over synthetic."""
from datetime import datetime, timezone, timedelta

from inbound_404 import (parse_404_csv, rerank, demand_tier, is_stale, _sev_from_hits)


# ── parsing: server log vs GSC ──
def test_server_log_format_has_hits_and_human_source():
    csv = "URL,Hits,Referrer\nhttps://acme.co/old-page,340,facebook.com\nhttps://acme.co/gone,12,\n"
    r = parse_404_csv(csv)
    assert r["source"] == "server_log" and r["count"] == 2
    top = r["records"][0]
    assert top["hits"] == 340 and "facebook.com" in top["top_referrers"]


def test_gsc_format_is_bot_demand_no_hit_column():
    csv = "URL,Last crawled,Response\nhttps://acme.co/dead,2026-06-01,404\nhttps://acme.co/dead,2026-06-02,404\n"
    r = parse_404_csv(csv)
    assert r["source"] == "gsc"
    assert r["records"][0]["hits"] == 2                 # two crawl-error rows → 2 bot hits (deduped-summed)
    assert any("Googlebot" in w for w in r["warnings"])


# ── normalization: strip tracking, preserve meaningful query, dedupe-sum ──
def test_tracking_stripped_meaningful_query_kept_and_merged():
    csv = ("URL,Hits\n"
           "https://acme.co/p?utm_source=fb&id=5,100\n"     # utm stripped → key /p?id=5
           "https://acme.co/p?id=5,50\n")                    # same normalized URL → merge
    r = parse_404_csv(csv)
    assert r["count"] == 1 and r["records"][0]["hits"] == 150
    assert "id=5" in r["records"][0]["url_normalized"] and "utm_source" not in r["records"][0]["url_normalized"]


def test_defensive_skips_junk_rows():
    csv = "URL,Hits\nTotal:,999\n,,\nhttps://acme.co/x,10\n"
    r = parse_404_csv(csv)
    assert r["count"] == 1 and r["skipped"] >= 1


# ── join + rerank ──
def _finding(url, priority="low"):
    return {"url": url, "priority": priority, "reason": "broken"}


def test_measured_ranks_above_synthetic_and_carries_hits():
    findings = [_finding("https://acme.co/a"), _finding("https://acme.co/b")]
    demand = parse_404_csv("URL,Hits\nhttps://acme.co/b,200\n")["records"]
    out = rerank(findings, demand)
    assert out["has_import"] is True
    assert out["measured"][0]["url"] == "https://acme.co/b" and out["measured"][0]["hits"] == 200
    assert out["measured"][0]["tier"] == "critical-demand" and out["measured"][0]["evidence"] == "measured"
    # /a had no import → stays estimated, priority untouched
    assert out["estimated"][0]["url"] == "https://acme.co/a" and "hits" not in out["estimated"][0]


def test_unmatched_import_becomes_ghost_class_hit_scaled():
    findings = [_finding("https://acme.co/a")]
    demand = parse_404_csv("URL,Hits,Referrer\nhttps://acme.co/ghost,80,an old newsletter\n")["records"]
    out = rerank(findings, demand)
    assert out["ghost_count"] == 1
    g = out["ghosts"][0]
    assert g["finding_class"] == "inbound_404" and g["severity"] == "high"     # 80 → high
    assert "no link on your site points here" in g["consequence"].lower()
    assert "an old newsletter" in g["top_referrers"]


def test_no_import_is_byte_identical_ordering():
    findings = [_finding("https://acme.co/a"), _finding("https://acme.co/b"), _finding("https://acme.co/c")]
    out = rerank(findings, [])
    assert out["has_import"] is False
    assert out["measured"] == [] and out["ghosts"] == []
    assert out["estimated"] == findings          # exact same list, same order
    assert out["verdict"] is None


def test_verdict_language_bot_vs_human():
    human = rerank([], parse_404_csv("URL,Hits\nhttps://a.co/x,10\n")["records"], source="server_log")
    assert human["verdict"].startswith("Real visitors hit")
    bot = rerank([], parse_404_csv("URL,Last crawled\nhttps://a.co/x,2026-06-01\n")["records"], source="gsc")
    assert bot["verdict"].startswith("Googlebot crawled")


# ── tiers, severity, staleness ──
def test_tiers_and_severity_bands():
    assert demand_tier(340) == "critical-demand" and demand_tier(50) == "high-demand" and demand_tier(5) == "noted"
    assert _sev_from_hits(100) == "critical" and _sev_from_hits(20) == "high" and _sev_from_hits(1) == "medium"


def test_staleness_at_60_days():
    old = (datetime.now(timezone.utc) - timedelta(days=70)).isoformat()
    fresh = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    assert is_stale(old) is True and is_stale(fresh) is False
