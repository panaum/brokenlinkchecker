"""Client intelligence — the four chips aggregated across a client's sites.

Sites resolve through the EXISTING sites.client_id FK. The load-bearing claims:
no second mapping authority is introduced, worst-of never hides a red, and the
aggregation matches the Dashboard's rule for rule.
"""
import inspect

from presence import aggregate_chip, client_presence_chips, site_chips, worst_state, CHIP_KEYS


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
    assert client_presence_chips([]) is None
    assert client_presence_chips(None) is None


def test_a_site_with_no_chips_contributes_nothing():
    assert client_presence_chips([("s1", "/dashboard/s1", [])]) is None


# ── single site ─────────────────────────────────────────────────────────────
def test_single_site_states_its_own_fact_without_counting():
    ci = client_presence_chips([_site("s1", ssl="critical")])
    by = {c["key"]: c for c in ci["chips"]}
    assert by["ssl"]["text"] == "3 days", "one site: no '1 of 1' noise"
    assert by["ssl"]["total"] == 1
    assert by["ssl"]["site_path"] == "/dashboard/s1"
    assert ci["site_count"] == 1


def test_all_four_chips_are_always_present():
    ci = client_presence_chips([_site("s1")])
    assert [c["key"] for c in ci["chips"]] == list(CHIP_KEYS)
    assert ci["worst"] == "ok"


# ── multi-site aggregation, each chip on its own axis ───────────────────────
def test_each_chip_aggregates_independently():
    ci = client_presence_chips([_site("a", ssl="warn"), _site("b", fragility="critical"), _site("c")])
    by = {c["key"]: c for c in ci["chips"]}
    assert by["ssl"]["state"] == "warn" and by["ssl"]["text"] == "⚠ on 1 of 3 sites"
    assert by["fragility"]["state"] == "critical" and by["fragility"]["text"] == "⚠ on 1 of 3 sites"
    assert by["sentinel"]["state"] == "ok" and by["sentinel"]["text"] == "ok on 3 sites"
    assert by["incidents"]["state"] == "ok"
    assert ci["worst"] == "critical"


def test_one_red_among_twenty_nine_greens_survives():
    sites = [_site(f"s{i}") for i in range(29)] + [_site("bad", incidents="critical")]
    ci = client_presence_chips(sites)
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
    ci = client_presence_chips([_site("a", sentinel="warn"), _site("b", ssl="notice")])
    assert ci["worst"] == worst_state([c["state"] for c in ci["chips"]])


def test_settling_client_does_not_read_as_healthy():
    ci = client_presence_chips([_site("a", fragility="settling")])
    assert ci["worst"] == "settling"


# ── the endpoint: existing FK, no new mapping, read-only ───────────────────
def test_endpoint_resolves_sites_through_the_existing_fk():
    import main
    src = inspect.getsource(main.registry_bridge_client_presence)
    assert "registry_client_sites" in src, "sites.client_id is the mapping — reuse it"
    for invented in ("client_sites_map", "client_site_map", "create table", "alter table"):
        assert invented not in src.lower(), f"no second mapping authority — found {invented!r}"


def test_endpoint_is_read_only_and_bulk():
    import main
    src = inspect.getsource(main.registry_bridge_client_presence)
    for forbidden in ("upsert", "insert", "enqueue(", "run_sentinel_for_site", ".update("):
        assert forbidden not in src
    for expected in ("sentinel_status_bulk", "open_incident_counts", "fragility_bulk"):
        assert expected in src, "three bulk reads — flat cost in site count"


def test_endpoint_is_flag_gated_before_any_work():
    import main
    src = inspect.getsource(main.registry_bridge_client_presence)
    # Anchor on the code expression — the docstring names the flag too, and the
    # deferred import sits above the gate. What matters is the CHECK vs the CALL.
    gate = src.index('os.getenv("PRESENCE_CHIPS")')
    assert gate < src.index("await registry_client_sites("), "flag is checked before the DB is touched"
    assert gate < src.index("await _qa_authenticate("), "…and before auth does any work"
    assert "status_code=404" in src[gate:gate + 200], "off ⇒ indistinguishable from not existing"


def _code_only(fn):
    """Function source with comments and docstring removed. These endpoints
    explain themselves in prose that names the very things the code must not do."""
    import io, tokenize
    src = inspect.getsource(fn)
    out, prev = [], tokenize.INDENT
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and prev in (tokenize.INDENT, tokenize.NEWLINE, tokenize.NL):
            continue
        out.append(tok.string)
        if tok.type not in (tokenize.NL, tokenize.NEWLINE):
            prev = tok.type
    return " ".join(out)


# ── still no composite ──────────────────────────────────────────────────────
def test_aggregation_blends_nothing():
    src = inspect.getsource(aggregate_chip) + inspect.getsource(client_presence_chips)
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
    ci = client_presence_chips([("s1", "/dashboard/s1", chips)])
    by = {c["key"]: c for c in ci["chips"]}
    assert by["incidents"]["state"] == "critical"
    assert by["fragility"]["state"] == "settling"
    assert ci["worst"] == "critical"


# ═══ Decision 2 — the display ranking is pinned ══════════════════════════════
def test_ranking_order_is_pinned_best_to_worst():
    """If a future change reorders severity, this fails. That is the point."""
    from presence import RANKING_BEST_FIRST, STATE_ORDER, state_label
    assert RANKING_BEST_FIRST == ("stable", "fresh", "drifting", "fragile", "brittle")
    # The display ranking IS the internal ladder, reversed. One order, two names.
    internal_best_first = tuple(s for s in reversed(STATE_ORDER) if s != "unknown")
    assert tuple(state_label(s) for s in internal_best_first) == RANKING_BEST_FIRST


def test_every_state_has_exactly_one_label():
    from presence import STATE_ORDER, state_label
    labels = [state_label(s) for s in STATE_ORDER]
    assert len(set(labels)) == len(labels), "no two states may share a label"
    assert state_label("unknown") == "unknown", "'could not tell' is not on the ranking"
    assert state_label("nonsense") == "unknown"


def test_worst_label_travels_with_worst():
    from presence import state_label
    ci = client_presence_chips([_site("a", incidents="critical")])
    assert ci["worst"] == "critical"
    assert ci["worst_label"] == "brittle" == state_label(ci["worst"])


# ═══ Decision 3 — counts-only sites summary, no names, no ids ════════════════
def test_sites_summary_counts_by_state_and_label():
    from presence import sites_summary
    s = sites_summary([_site("a"), _site("b", ssl="critical"), _site("c", fragility="settling")])
    assert s["total"] == 3
    assert s["by_state"] == {"ok": 1, "critical": 1, "settling": 1}
    assert s["by_label"] == {"stable": 1, "brittle": 1, "fresh": 1}


def test_sites_summary_leaks_no_identity():
    from presence import sites_summary
    s = sites_summary([_site("secret-site-id"), _site("another-id", ssl="warn")])
    flat = repr(s)
    assert "secret-site-id" not in flat and "another-id" not in flat
    assert "/dashboard/" not in flat, "no site paths in the summary either"


def test_endpoint_returns_summary_not_a_per_site_map():
    import main
    src = inspect.getsource(main.registry_bridge_client_presence)
    assert "sites_summary" in src
    assert '"sites": {' not in src, "per-site detail is reached by handoff, not smuggled in the payload"


# ═══ Decision 4 — Fresh Mode leaks nothing ══════════════════════════════════
def test_fresh_mode_tooltip_reports_days_monitored():
    chip = {c["key"]: c for c in site_chips({}, 0, {"insufficient": True,
                                                    "gate": {"have_days": 34, "have_scans": 5}})}["fragility"]
    assert chip["state"] == "settling"
    assert chip["text"] == "settling"
    assert chip["detail"] == "34 days monitored · pattern still forming"
    assert chip.get("fresh_mode") is True


def test_fresh_mode_singular_day():
    chip = {c["key"]: c for c in site_chips({}, 0, {"insufficient": True,
                                                    "gate": {"have_days": 1}})}["fragility"]
    assert chip["detail"] == "1 day monitored · pattern still forming"


def test_fresh_mode_never_leaks_a_partial_score_or_band():
    """Even if a gated row carries a provisional score, none of it may render."""
    gated = {"insufficient": True, "score": 71, "band": "brittle",
             "factors": ["9 breakages"], "gate": {"have_days": 12}}
    chip = {c["key"]: c for c in site_chips({}, 0, gated)}["fragility"]
    flat = repr(chip)
    assert "71" not in flat and "brittle" not in flat and "breakages" not in flat
    assert chip["text"] == "settling"


def test_unknown_history_still_says_pattern_forming():
    chip = {c["key"]: c for c in site_chips({}, 0, None)}["fragility"]
    assert chip["detail"] == "Pattern still forming"


# ═══ Decision 5 — the one deliberate write ══════════════════════════════════
def test_link_client_is_flag_gated_and_service_keyed():
    import main
    src = inspect.getsource(main.registry_bridge_link_client)
    gate = src.index('os.getenv("PRESENCE_CHIPS")')
    assert gate < src.index("await _qa_authenticate("), "flag precedes auth"
    assert "status_code=404" in src[gate:gate + 200]


def test_link_client_verifies_an_explicit_id_before_trusting_it():
    import main
    src = inspect.getsource(main.registry_bridge_link_client)
    assert "registry_client_by_id" in src
    assert "status_code=404" in src.split("if explicit:")[1][:400], \
        "a wrong paste must fail loudly, not annotate the wrong client forever"


def test_link_client_matches_by_name_before_creating_a_duplicate():
    import main
    src = inspect.getsource(main.registry_bridge_link_client)
    assert src.index("registry_client_by_name") < src.index("await create_client("), \
        "creating a duplicate registry client is the expensive mistake (§8.2: ids are eternal)"


def test_no_bulk_linking_path_exists():
    """Linking is one client, one human, one press — by construction."""
    import main
    code = _code_only(main.registry_bridge_link_client)
    for bulk in ("for client in", "list_clients(", "all_clients", "for c in"):
        assert bulk not in code, f"no sweep may exist — found {bulk!r}"
    # Exactly one create call, reached only after the id and name lookups fail.
    assert code.count("create_client") == 2, "one import, one call — no second creation path"


def test_link_client_is_the_only_write_in_the_feature():
    import main
    for fn in (main.registry_bridge_client_presence, main.qa_bridge_presence_sites,
               main.qa_bridge_presence):
        src = inspect.getsource(fn)
        for w in ("create_client", "insert", "upsert", ".update("):
            assert w not in src, f"{fn.__name__} must stay read-only — found {w!r}"
