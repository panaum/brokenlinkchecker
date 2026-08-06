"""Client presence chips — four honest signals per site, no composite anywhere.

The load-bearing claims under test: presence invents no threshold of its own,
`sentinel` never repeats SSL or uptime, fresh sites read 'settling' rather than
a score, and worst-of never hides a red.
"""
import inspect
from datetime import datetime, timezone, timedelta

from presence import site_chips, worst_state, STATE_ORDER, CHIP_KEYS
from sentinel import LADDER, escalation


def _iso(days):
    return (datetime.now(timezone.utc) + timedelta(days=days, hours=6)).isoformat()


def _by_key(chips):
    return {c["key"]: c for c in chips}


HEALTHY = {"ssl_expiry": _iso(200), "domain_expiry": _iso(300), "robots_ok": True,
           "meta_noindex": False, "header_noindex": False, "sitemap_ok": True}


# ── shape ───────────────────────────────────────────────────────────────────
def test_always_four_chips_in_a_stable_order():
    chips = site_chips(HEALTHY, 0, {"score": 10, "band": "sturdy"})
    assert [c["key"] for c in chips] == list(CHIP_KEYS) == ["ssl", "sentinel", "incidents", "fragility"]


def test_a_site_with_no_data_at_all_still_returns_four_chips():
    chips = _by_key(site_chips(None, 0, None))
    assert len(chips) == 4
    assert chips["ssl"]["state"] == "unknown"
    assert chips["fragility"]["state"] == "settling"
    assert chips["incidents"]["state"] == "ok"


def test_every_chip_carries_its_own_state_never_a_shared_one():
    chips = _by_key(site_chips({**HEALTHY, "ssl_expiry": _iso(2)}, 0, {"score": 10, "band": "sturdy"}))
    assert chips["ssl"]["state"] == "critical"
    assert chips["sentinel"]["state"] == "ok", "a bad SSL must not colour the sentinel chip"
    assert chips["fragility"]["state"] == "ok"


# ── thresholds are inherited, not invented ──────────────────────────────────
def test_ssl_ladder_is_exactly_sentinels_ladder():
    assert LADDER == (30, 14, 3)
    for days, expected in ((2, "critical"), (10, "warn"), (25, "notice"), (90, "ok")):
        chips = _by_key(site_chips({**HEALTHY, "ssl_expiry": _iso(days)}, 0, None))
        assert chips["ssl"]["state"] == expected == escalation(days)


def test_presence_module_defines_no_day_thresholds_of_its_own():
    src = inspect.getsource(__import__("presence"))
    for invented in ("<= 3", "<= 14", "<= 30", "60 <", "days > 30"):
        assert invented not in src, f"presence must not restate a ladder — found {invented!r}"


# ── the sentinel chip: domain + visibility ONLY ─────────────────────────────
def test_sentinel_chip_reflects_domain_expiry():
    chips = _by_key(site_chips({**HEALTHY, "domain_expiry": _iso(2)}, 0, None))
    assert chips["sentinel"]["state"] == "critical"
    assert chips["sentinel"]["text"] == "domain 2 days"


def test_sentinel_chip_reflects_search_visibility():
    chips = _by_key(site_chips({**HEALTHY, "meta_noindex": True}, 0, None))
    assert chips["sentinel"]["state"] == "critical"
    assert chips["sentinel"]["text"] == "search visibility"


def test_sentinel_chip_never_repeats_ssl():
    """SSL earns its own chip; rolling it in would hide the most fixable date."""
    chips = _by_key(site_chips({**HEALTHY, "ssl_expiry": _iso(1)}, 0, None))
    assert chips["ssl"]["state"] == "critical"
    assert chips["sentinel"]["state"] == "ok"


def test_sentinel_chip_never_repeats_uptime():
    """An open incident IS the uptime verdict — counting both prints one
    outage twice, in two colours."""
    chips = _by_key(site_chips(HEALTHY, 3, None))
    assert chips["incidents"]["state"] == "critical"
    assert chips["incidents"]["text"] == "3 open"
    assert chips["sentinel"]["state"] == "ok"


def test_presence_never_reads_uptime_pings():
    src = inspect.getsource(__import__("presence"))
    assert "uptime_pings" not in src and "recent_pings" not in src
    assert "downtime_state" not in src, "downtime lives in the incidents chip"


# ── fragility: settling, bands, and the factors rule ────────────────────────
def test_fresh_site_reads_settling_with_the_gates_own_reason():
    chip = _by_key(site_chips(HEALTHY, 0, {"insufficient": True,
                                           "gate": {"have_days": 34, "have_scans": 5}}))["fragility"]
    assert chip["state"] == "settling"
    assert chip["text"] == "settling", "a fresh site shows no score at all"
    # Fresh Mode (decision 4): days monitored only — never the gate's thresholds,
    # never a partial score.
    assert chip["detail"] == "34 days monitored · pattern still forming"
    assert chip["fresh_mode"] is True


def test_absent_fragility_row_is_settling_not_healthy():
    chip = _by_key(site_chips(HEALTHY, 0, None))["fragility"]
    assert chip["state"] == "settling"
    assert chip["detail"] == "Pattern still forming"


def test_fragility_bands_map_to_states_with_normal_as_notice():
    """`normal` covers the middle 34 points and describes most healthy sites —
    painting the median amber would train the team to ignore amber."""
    for band, expected in (("sturdy", "ok"), ("normal", "notice"), ("brittle", "critical")):
        chip = _by_key(site_chips(HEALTHY, 0, {"score": 40, "band": band}))["fragility"]
        assert chip["state"] == expected


def test_fragility_chip_carries_its_factors():
    """The factors rule is absolute upstream; presence must not drop them."""
    chip = _by_key(site_chips(HEALTHY, 0, {"score": 72, "band": "brittle",
                                           "factors": ["9 breakages in 90 days", "median fix 6 days"]}))["fragility"]
    assert chip["text"] == "72 · brittle"
    assert chip["detail"] == "9 breakages in 90 days · median fix 6 days"


# ── worst-of: the only reduction, and it never hides a red ──────────────────
def test_worst_of_ladder_order():
    assert STATE_ORDER == ("critical", "warn", "notice", "settling", "unknown", "ok")
    assert worst_state(["ok", "critical", "notice"]) == "critical"
    assert worst_state(["ok", "notice"]) == "notice"
    assert worst_state(["ok", "ok"]) == "ok"
    assert worst_state([]) == "unknown"
    assert worst_state(["nonsense"]) == "unknown"


def test_settling_is_neither_a_red_nor_a_green():
    assert worst_state(["ok", "settling"]) == "settling", "settling must not read as healthy"
    assert worst_state(["notice", "settling"]) == "notice", "settling must not read as a problem"
    assert worst_state(["critical", "settling"]) == "critical"


def test_one_red_among_many_greens_survives():
    states = ["ok"] * 30 + ["critical"]
    assert worst_state(states) == "critical"


# ── no composite, anywhere ──────────────────────────────────────────────────
def test_no_chip_carries_a_blended_number():
    chips = site_chips(HEALTHY, 2, {"score": 72, "band": "brittle"})
    for c in chips:
        assert "score" not in c or c["key"] == "fragility"
    # The only number that survives is fragility's own, and it is named.
    assert _by_key(chips)["fragility"]["text"] == "72 · brittle"


def _code_only(module_name):
    """Source with comments and docstrings removed — these files explain
    themselves in prose that names the very things the code must not do."""
    import io, tokenize
    src = inspect.getsource(__import__(module_name))
    out, prev_type = [], tokenize.INDENT
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and prev_type in (tokenize.INDENT, tokenize.NEWLINE, tokenize.NL):
            continue  # docstring
        out.append(tok.string)
        if tok.type not in (tokenize.NL, tokenize.NEWLINE):
            prev_type = tok.type
    return " ".join(out)


def test_presence_computes_no_weighted_roll_up():
    """Counting (`sum(1 for …)`) is fine; blending is not. The distinction is
    the whole point: a count names its cause, a weighted score does not."""
    code = _code_only("presence")
    for banned in ("weight", "* 0.", "/ len(", "mean(", "average", "composite", "W_RATE"):
        assert banned not in code, f"no composite may exist in presence — found {banned!r}"
    # Presence never invokes the scoring engine: it reads a stored row and
    # renders it. Any score it shows was computed and justified elsewhere.
    for engine in ("fragility_score", "compute_metrics", "import fragility"):
        assert engine not in code, f"presence must read scores, never produce them — found {engine!r}"


# ── T4 / read-only ──────────────────────────────────────────────────────────
def test_chips_endpoint_is_read_only_and_bulk():
    import main
    src = inspect.getsource(main.qa_bridge_presence_sites)
    for forbidden in ("upsert", "insert", "enqueue(", "run_sentinel_for_site", "open_incident("):
        assert forbidden not in src
    for expected in ("sentinel_status_bulk", "open_incident_counts", "fragility_bulk"):
        assert expected in src, "three bulk reads — cost must be flat in site count"


def test_endpoint_reports_truncation_rather_than_hiding_it():
    import main
    src = inspect.getsource(main.qa_bridge_presence_sites)
    assert "truncated" in src and "dropped" in src, "a cap that lies about coverage is worse than none"
