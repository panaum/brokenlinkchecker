"""Client intelligence — the four chips aggregated across a client's sites.

Sites resolve through the EXISTING sites.client_id FK. The load-bearing claims:
no second mapping authority is introduced, worst-of never hides a red, and the
aggregation matches the Dashboard's rule for rule.
"""
import inspect

from presence import aggregate_chip, client_intelligence, site_chips, worst_state, CHIP_KEYS


def _chips(**states):
    """A per-site chip list with the given states; everything else ok."""
    labels = {"ssl": "SSL", "sentinel": "Sentinel", "incidents": "Incidents", "fragility": "Fragility"}
    return [{"key": k, "state": states.get(k, "ok"), "label": labels[k],
             "text": "3 days" if states.get(k, "ok") != "ok" else "ok",
             "detail": f"{k} detail"} for k in CHIP_KEYS]


def _site(sid, **states):
    return (sid, f"/dashboard/{sid}", _chips(**states))


# ── no sites ────────────────────────────────────────────────────────────────
def test_a_client_with_no_sites_returns_none():
    assert client_intelligence([]) is None
    assert client_intelligence(None) is None


def test_a_site_with_no_chips_contributes_nothing():
    assert client_intelligence([("s1", "/dashboard/s1", [])]) is None


# ── single site ─────────────────────────────────────────────────────────────
def test_single_site_states_its_own_fact_without_counting():
    ci = client_intelligence([_site("s1", ssl="critical")])
    by = {c["key"]: c for c in ci["chips"]}
    assert by["ssl"]["text"] == "3 days", "one site: no '1 of 1' noise"
    assert by["ssl"]["total"] == 1
    assert by["ssl"]["site_path"] == "/dashboard/s1"
    assert ci["site_count"] == 1


def test_all_four_chips_are_always_present():
    ci = client_intelligence([_site("s1")])
    assert [c["key"] for c in ci["chips"]] == list(CHIP_KEYS)
    assert ci["worst"] == "ok"


# ── multi-site aggregation, each chip on its own axis ───────────────────────
def test_each_chip_aggregates_independently():
    ci = client_intelligence([_site("a", ssl="warn"), _site("b", fragility="critical"), _site("c")])
    by = {c["key"]: c for c in ci["chips"]}
    assert by["ssl"]["state"] == "warn" and by["ssl"]["text"] == "⚠ on 1 of 3 sites"
    assert by["fragility"]["state"] == "critical" and by["fragility"]["text"] == "⚠ on 1 of 3 sites"
    assert by["sentinel"]["state"] == "ok" and by["sentinel"]["text"] == "ok on 3 sites"
    assert by["incidents"]["state"] == "ok"
    assert ci["worst"] == "critical"


def test_one_red_among_twenty_nine_greens_survives():
    sites = [_site(f"s{i}") for i in range(29)] + [_site("bad", incidents="critical")]
    ci = client_intelligence(sites)
    inc = {c["key"]: c for c in ci["chips"]}["incidents"]
    assert inc["state"] == "critical", "greens must never outvote a red"
    assert inc["text"] == "⚠ on 1 of 30 sites"
    assert ci["worst"] == "critical"


def test_affected_counts_sites_at_the_worst_state():
    chip = aggregate_chip("ssl", [_site("a", ssl="critical"), _site("b", ssl="critical"), _site("c")])
    assert (chip["affected"], chip["total"]) == (2, 3)
    assert chip["text"] == "⚠ on 2 of 3 sites"


# ── deep links and detail: only when one site is implicated ─────────────────
def test_detail_and_link_only_when_a_single_site_is_implicated():
    one = aggregate_chip("ssl", [_site("a", ssl="critical"), _site("b")])
    assert one["site_path"] == "/dashboard/a"
    assert one["detail"] == "ssl detail"

    many = aggregate_chip("ssl", [_site("a", ssl="critical"), _site("b", ssl="critical")])
    assert many["site_path"] is None, "pointing 'two sites' at one of them would be a lie"
    assert many["detail"] is None


# ── worst-of is over the AGGREGATED chips ──────────────────────────────────
def test_headline_can_never_disagree_with_the_chips_it_shows():
    ci = client_intelligence([_site("a", sentinel="warn"), _site("b", ssl="notice")])
    assert ci["worst"] == worst_state([c["state"] for c in ci["chips"]])


def test_settling_client_does_not_read_as_healthy():
    ci = client_intelligence([_site("a", fragility="settling")])
    assert ci["worst"] == "settling"


# ── the endpoint: existing FK, no new mapping, read-only ───────────────────
def test_endpoint_resolves_sites_through_the_existing_fk():
    import main
    src = inspect.getsource(main.qa_bridge_client_intelligence)
    assert "registry_client_sites" in src, "sites.client_id is the mapping — reuse it"
    for invented in ("client_sites_map", "client_site_map", "create table", "alter table"):
        assert invented not in src.lower(), f"no second mapping authority — found {invented!r}"


def test_endpoint_is_read_only_and_bulk():
    import main
    src = inspect.getsource(main.qa_bridge_client_intelligence)
    for forbidden in ("upsert", "insert", "enqueue(", "run_sentinel_for_site", ".update("):
        assert forbidden not in src
    for expected in ("sentinel_status_bulk", "open_incident_counts", "fragility_bulk"):
        assert expected in src, "three bulk reads — flat cost in site count"


def test_endpoint_is_flag_gated_before_any_work():
    import main
    src = inspect.getsource(main.qa_bridge_client_intelligence)
    # Anchor on the code expression — the docstring names the flag too, and the
    # deferred import sits above the gate. What matters is the CHECK vs the CALL.
    gate = src.index('os.getenv("CLIENT_INTELLIGENCE")')
    assert gate < src.index("await registry_client_sites("), "flag is checked before the DB is touched"
    assert gate < src.index("await _qa_authenticate("), "…and before auth does any work"
    assert "status_code=404" in src[gate:gate + 200], "off ⇒ indistinguishable from not existing"


def test_aggregate_carries_per_site_detail_for_audit():
    import main
    src = inspect.getsource(main.qa_bridge_client_intelligence)
    assert '"sites":' in src, "an aggregate must stay auditable back to its sites"


# ── still no composite ──────────────────────────────────────────────────────
def test_aggregation_blends_nothing():
    src = inspect.getsource(aggregate_chip) + inspect.getsource(client_intelligence)
    for banned in ("weight", "* 0.", "/ len(", "mean(", "average", "composite", "score"):
        assert banned not in src, f"no composite may exist — found {banned!r}"


# ── parity with the Dashboard implementation ───────────────────────────────
def test_text_formats_match_the_dashboard_rule_set():
    """Both sides must print the same strings for the same facts; these exact
    forms are asserted in the Dashboard's chips.test.ts too."""
    assert aggregate_chip("ssl", [_site("a", ssl="warn"), _site("b"), _site("c")])["text"] == "⚠ on 1 of 3 sites"
    assert aggregate_chip("ssl", [_site("a"), _site("b"), _site("c")])["text"] == "ok on 3 sites"
    assert aggregate_chip("ssl", [_site("a", ssl="critical")])["text"] == "3 days"


def test_site_chips_still_feed_the_aggregate_unchanged():
    """The client route reuses site_chips() — the per-site contract is the same
    one the presence/sites endpoint already serves."""
    chips = site_chips({"ssl_expiry": None}, 2, None)
    ci = client_intelligence([("s1", "/dashboard/s1", chips)])
    by = {c["key"]: c for c in ci["chips"]}
    assert by["incidents"]["state"] == "critical"
    assert by["fragility"]["state"] == "settling"
    assert ci["worst"] == "critical"
