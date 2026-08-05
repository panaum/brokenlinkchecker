"""Cross-app PRESENCE (Seam 3) — signal shaping for the Deliverables-side
production strip, plus a guard that the read path can never probe or write."""
import inspect

from presence import presence_signals, open_incident_count, ATTENTION
from sentinel import summarize_sentinel


def _cards(**escalations):
    """A summarize_sentinel-shaped payload with the escalations we care about."""
    order = {"ssl": ("SSL", 3), "domain": ("Domain", 9), "index": ("Search visibility", None),
             "uptime": ("Uptime", None)}
    cards = []
    for key, esc in escalations.items():
        label, days = order[key]
        cards.append({"key": key, "label": label, "days": days, "escalation": esc,
                      "fact": f"{days} days" if days is not None else "—"})
    return {"cards": cards, "down": False}


# ── the quiet default ──
def test_healthy_site_produces_no_signals_at_all():
    """No strip is rendered from []. There is deliberately no 'all good' state."""
    assert presence_signals(_cards(ssl="ok", domain="ok", index="ok", uptime="ok"), []) == []


def test_notice_tier_stays_quiet():
    """30-day horizon is a calendar entry, not something to raise at sign-off."""
    assert presence_signals(_cards(ssl="notice", domain="notice"), []) == []
    assert "notice" not in ATTENTION


def test_unknown_tier_stays_quiet():
    assert presence_signals(_cards(ssl="unknown", index="unknown"), []) == []


def test_missing_sentinel_payload_is_not_a_crash():
    assert presence_signals(None, None) == []
    assert presence_signals({}, []) == []


# ── one signal ──
def test_single_warn_card_renders_one_line():
    sigs = presence_signals(_cards(ssl="critical", domain="ok"), [])
    assert len(sigs) == 1
    assert sigs[0]["text"] == "SSL certificate expires in 3 days"
    assert sigs[0]["qualifier"] == "monitoring holding"
    assert sigs[0]["severity"] == "critical"


def test_expired_reads_as_expired_not_negative_days():
    payload = {"cards": [{"key": "domain", "label": "Domain", "days": -4, "escalation": "critical"}]}
    assert presence_signals(payload, [])[0]["text"] == "Domain registration has expired"


def test_one_open_incident_is_singular_and_names_its_watcher():
    sigs = presence_signals(_cards(), [{"id": "i1", "down_at": "x", "restored_at": None}])
    assert sigs[0]["text"] == "1 open incident"
    assert sigs[0]["qualifier"] == "disaster sentinel"


def test_resolved_incidents_are_not_signals():
    incidents = [{"id": "i1", "down_at": "x", "restored_at": "y"},
                 {"id": "i2", "down_at": "x", "restored_at": "y"}]
    assert open_incident_count(incidents) == 0
    assert presence_signals(_cards(), incidents) == []


# ── several signals ──
def test_three_signals_sort_critical_before_warn():
    sigs = presence_signals(_cards(ssl="warn", index="critical"),
                            [{"id": "i1", "restored_at": None}])
    assert [s["severity"] for s in sigs] == ["critical", "critical", "warn"]
    assert sigs[0]["text"] == "1 open incident"          # incidents lead
    assert [s["key"] for s in sigs] == ["incident", "index", "ssl"]


def test_open_incident_suppresses_the_duplicate_uptime_card():
    """Both say 'the site is down'; the incident line is the one with duration."""
    sigs = presence_signals(_cards(uptime="critical"), [{"id": "i1", "restored_at": None}])
    assert [s["key"] for s in sigs] == ["incident"]


def test_uptime_card_still_speaks_when_no_incident_is_open():
    sigs = presence_signals(_cards(uptime="critical"), [])
    assert [s["key"] for s in sigs] == ["uptime"]
    assert sigs[0]["text"] == "Site is not responding"


def test_down_site_qualifier_is_honest():
    payload = _cards(ssl="critical")
    payload["down"] = True
    assert presence_signals(payload, [])[0]["qualifier"] == "site is down"


# ── the socket rule: a new sentinel check surfaces without touching presence.py ──
def test_an_unrecognised_card_key_still_renders_a_line():
    payload = {"cards": [{"key": "cwv", "label": "Core Web Vitals",
                          "escalation": "warn", "fact": "LCP 4.8s"}]}
    assert presence_signals(payload, [])[0]["text"] == "Core Web Vitals: LCP 4.8s"


# ── deep links ──
def test_every_signal_carries_the_app_relative_path_for_signing():
    sigs = presence_signals(_cards(ssl="critical"), [{"id": "i", "restored_at": None}],
                            site_path="/dashboard/site-1")
    assert sigs and all(s["deep_link_path"] == "/dashboard/site-1" for s in sigs)


# ── real summarize_sentinel output flows through unchanged ──
def test_consumes_the_real_summarize_sentinel_payload():
    from datetime import datetime, timezone, timedelta
    # days_until floors, so pad past the boundary to pin an exact "2 days".
    soon = (datetime.now(timezone.utc) + timedelta(days=2, hours=6)).isoformat()
    summary = summarize_sentinel({"ssl_expiry": soon, "ssl_issuer": "R3",
                                  "robots_ok": True, "meta_noindex": False,
                                  "header_noindex": False, "sitemap_ok": True}, [True, True])
    sigs = presence_signals(summary, [])
    assert [s["key"] for s in sigs] == ["ssl"]
    assert sigs[0]["text"] == "SSL certificate expires in 2 days"


# ── T4: the presence path is READ-ONLY ──
def test_presence_module_performs_no_io():
    src = inspect.getsource(__import__("presence"))
    for forbidden in ("import requests", "httpx", "await ", "insert(", "update(",
                      "delete(", "supabase", "os.getenv"):
        assert forbidden not in src, f"presence.py must stay pure — found {forbidden!r}"


def test_endpoint_never_runs_a_scan_or_probe_or_write():
    import main
    src = inspect.getsource(main.qa_bridge_presence)
    # Call-shaped tokens: `open_incident_count` is a pure counter, not a writer.
    for forbidden in ("run_sentinel_for_site", "run_uptime_for_site", "enqueue(",
                      "upsert", "insert", "open_incident(", "close_incident("):
        assert forbidden not in src, f"presence endpoint must stay read-only — found {forbidden!r}"
    # It reads exactly the three stored sources and nothing else.
    for expected in ("get_sentinel_status", "recent_pings", "list_incidents"):
        assert expected in src
