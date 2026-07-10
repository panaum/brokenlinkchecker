"""
Third-party watchdog.

The promises being pinned:

  - one dead shared host across N sites is ONE alert naming all N, never N alerts
  - the same outage is not re-announced within the dedupe window
  - a third-party outage is NEVER the client's broken link — it is demoted to
    unverifiable so it cannot turn their report red
  - a 403/429 bot-block is not an outage
"""
import asyncio

import pytest

import watchdog as W
from watchdog import (
    aggregate_outages,
    demote_third_party_failures,
    format_outage_alert,
    host_failed,
    inventory_hosts,
    is_third_party,
    outages_to_alert,
    run_watchdog,
)

PAGE = "https://www.acme.test/pricing"


class _Res:
    def __init__(self, url, resource_type="script", bucket="ok",
                 status_code=200, is_external=True):
        self.url = url
        self.resource_type = resource_type
        self.bucket = bucket
        self.status_code = status_code
        self.is_external = is_external
        self.label = "ok"
        self.priority = "low"
        self.error = None
        self.reason = ""


# ─── third-party detection ───────────────────────────────────────────────────
def test_a_known_widget_host_is_third_party():
    assert is_third_party("https://assets.calendly.com/w.js", PAGE) is True
    assert is_third_party("https://js.hs-scripts.com/1.js", PAGE) is True


def test_a_cross_domain_host_is_third_party():
    assert is_third_party("https://cdn.other.test/a.js", PAGE) is True


def test_the_sites_own_host_is_not_third_party():
    assert is_third_party("https://www.acme.test/app.js", PAGE) is False
    assert is_third_party("https://acme.test/app.js", PAGE) is False


# ─── host failure detection ──────────────────────────────────────────────────
@pytest.mark.parametrize("status", [500, 502, 503, 504, 404, 410])
def test_a_server_error_status_is_a_host_failure(status):
    assert host_failed(_Res("https://x.test/a.js", bucket="broken", status_code=status))


def test_a_dns_dead_host_is_a_failure():
    assert host_failed(_Res("https://gone.test/a.js", bucket="broken", status_code=None))


@pytest.mark.parametrize("status", [403, 429, 401, 999])
def test_a_bot_block_is_not_a_host_failure(status):
    assert host_failed(_Res("https://x.test/a.js", bucket="blocked", status_code=status)) is False


def test_a_healthy_host_is_not_a_failure():
    assert host_failed(_Res("https://x.test/a.js", bucket="ok", status_code=200)) is False


# ─── inventory ───────────────────────────────────────────────────────────────
def test_inventory_collects_third_party_scripts_and_iframes():
    results = [
        _Res("https://assets.calendly.com/widget.js", "script"),
        _Res("https://www.youtube.com/embed/x", "iframe"),
        _Res("https://www.acme.test/own.js", "script", is_external=False),  # first-party
        _Res("https://www.acme.test/logo.png", "image"),                    # not watched
    ]
    hosts = {h["host"] for h in inventory_hosts(results, PAGE)}
    assert "assets.calendly.com" in hosts
    assert "www.youtube.com" in hosts
    assert "www.acme.test" not in hosts


def test_inventory_marks_a_down_host():
    results = [_Res("https://calendly.com/w.js", "script", bucket="broken", status_code=503)]
    rec = inventory_hosts(results, PAGE)[0]
    assert rec["down"] is True and rec["status"] == 503


def test_inventory_dedupes_a_host_to_its_worst_status():
    results = [
        _Res("https://calendly.com/a.js", "script", bucket="ok", status_code=200),
        _Res("https://calendly.com/b.js", "script", bucket="broken", status_code=503),
    ]
    recs = inventory_hosts(results, PAGE)
    assert len(recs) == 1 and recs[0]["down"] is True


# ─── the link-verdict demotion (item 3) ──────────────────────────────────────
def test_a_dead_third_party_script_is_demoted_not_broken():
    results = [_Res("https://calendly.com/w.js", "script", bucket="broken", status_code=503)]
    assert demote_third_party_failures(results, PAGE) == 1
    assert results[0].bucket == "unverifiable"
    assert results[0].priority is None
    assert "their outage" in results[0].reason


def test_a_first_party_broken_script_is_left_alone():
    """The client's own broken asset is still their problem to fix — stays red."""
    results = [_Res("https://www.acme.test/app.js", "script", bucket="broken",
                    status_code=404, is_external=False)]
    assert demote_third_party_failures(results, PAGE) == 0
    assert results[0].bucket == "broken"


def test_a_bot_blocked_third_party_is_not_demoted_because_it_was_not_broken():
    results = [_Res("https://calendly.com/w.js", "script", bucket="blocked", status_code=403)]
    assert demote_third_party_failures(results, PAGE) == 0


# ─── cross-site aggregation: ONE alert, all sites ────────────────────────────
def _row(host, site_id, client, down=True, status=503):
    return {"host": host, "site_id": site_id, "client": client,
            "site_url": f"https://{client}.test", "down": down, "status": status,
            "resource_type": "script"}


def test_one_dead_shared_host_on_three_sites_is_one_outage_naming_all_three():
    inventory = [
        _row("calendly.com", "s1", "apexure"),
        _row("calendly.com", "s2", "fautons"),
        _row("calendly.com", "s3", "acme"),
    ]
    outages = aggregate_outages(inventory)
    assert len(outages) == 1
    assert len(outages[0]["sites"]) == 3
    clients = {s["client"] for s in outages[0]["sites"]}
    assert clients == {"apexure", "fautons", "acme"}


def test_the_alert_text_names_every_client_once():
    outage = aggregate_outages([_row("calendly.com", "s1", "apexure"),
                                _row("calendly.com", "s2", "fautons")])[0]
    text = format_outage_alert(outage)
    assert "calendly.com" in text and "apexure" in text and "fautons" in text
    assert "2 sites" in text
    assert "not the clients' sites" in text


def test_a_healthy_host_produces_no_outage():
    assert aggregate_outages([_row("calendly.com", "s1", "apexure", down=False)]) == []


def test_two_different_dead_hosts_are_two_outages():
    outages = aggregate_outages([_row("calendly.com", "s1", "apexure"),
                                 _row("intercom.io", "s1", "apexure")])
    assert len(outages) == 2


# ─── dedupe within the window ────────────────────────────────────────────────
NOW = 1_000_000.0


def test_a_host_alerted_an_hour_ago_is_suppressed():
    outages = aggregate_outages([_row("calendly.com", "s1", "apexure")])
    recent = {"calendly.com": NOW - 3600}         # 1h ago, window is 24h
    assert outages_to_alert(outages, recent, NOW, window_hours=24) == []


def test_a_host_alerted_two_days_ago_alerts_again():
    outages = aggregate_outages([_row("calendly.com", "s1", "apexure")])
    recent = {"calendly.com": NOW - 2 * 86400}
    assert len(outages_to_alert(outages, recent, NOW, window_hours=24)) == 1


def test_a_never_alerted_host_alerts():
    outages = aggregate_outages([_row("calendly.com", "s1", "apexure")])
    assert len(outages_to_alert(outages, {}, NOW)) == 1


# ─── orchestration: exactly one alert, then suppressed on re-scan ────────────
def test_run_watchdog_fires_one_alert_and_records_it():
    inventory = [_row("calendly.com", "s1", "apexure"),
                 _row("calendly.com", "s2", "fautons"),
                 _row("calendly.com", "s3", "acme")]
    sent, recorded = [], []

    async def go():
        return await run_watchdog(
            get_inventory=lambda: _async(inventory),
            get_recently_alerted=lambda: _async({}),
            record_alert=lambda host, ts: _async(recorded.append(host)),
            notify=lambda text, outage: _async(sent.append(text)),
            now_ts=NOW,
        )

    result = asyncio.run(go())
    assert result["alerted"] == 1
    assert len(sent) == 1                          # ONE alert, not three
    assert "apexure" in sent[0] and "fautons" in sent[0] and "acme" in sent[0]
    assert recorded == ["calendly.com"]


def test_run_watchdog_suppresses_a_rescan_within_the_window():
    inventory = [_row("calendly.com", "s1", "apexure")]
    sent = []

    async def go():
        return await run_watchdog(
            get_inventory=lambda: _async(inventory),
            get_recently_alerted=lambda: _async({"calendly.com": NOW - 3600}),
            record_alert=lambda host, ts: _async(None),
            notify=lambda text, outage: _async(sent.append(text)),
            now_ts=NOW,
        )

    result = asyncio.run(go())
    assert result["alerted"] == 0 and result["suppressed"] == 1
    assert sent == []                              # no duplicate alert


async def _async(value):
    return value


# ─── the endpoint groups up and down hosts, outages first ────────────────────
def test_the_hosts_endpoint_groups_and_orders(monkeypatch):
    import main
    inventory = [
        _row("calendly.com", "s1", "apexure", down=True, status=503),
        _row("calendly.com", "s2", "fautons", down=True, status=503),
        _row("googletagmanager.com", "s1", "apexure", down=False, status=200),
    ]

    async def fake_inventory():
        return inventory

    monkeypatch.setattr(main, "get_watchdog_inventory", fake_inventory)
    data = asyncio.run(main.watchdog_hosts())
    assert data["total_hosts"] == 2
    assert data["outages"] == 1
    # Down host first, and it names both affected sites.
    assert data["hosts"][0]["host"] == "calendly.com"
    assert data["hosts"][0]["down"] is True
    assert data["hosts"][0]["affected_sites"] == 2
    assert data["hosts"][1]["host"] == "googletagmanager.com"
    assert data["hosts"][1]["down"] is False
