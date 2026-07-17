"""Phase 5 — the deterministic gap classifier + absorption logic."""
from flywheel import (classify_gap, absorption_outcome, COVERAGE, CANDIDATE_TEMPLATES,
                      FLYWHEEL_MAP_VERSION)


# ── covered classes: drift (passed) vs process (missed) ──
def test_covered_and_passed_is_drift_no_candidate():
    r = classify_gap("sentinel_ssl", covered_passed_at_delivery=True)
    assert r["verdict"] == "drift" and "candidate" not in r
    assert r["covered_by"] == ("ssl_valid", "ssl_expiry")


def test_covered_but_missed_is_process_no_candidate():
    r = classify_gap("finding_broken", covered_passed_at_delivery=False)
    assert r["verdict"] == "process" and "candidate" not in r
    assert r["covered_by"] == ("broken_links",)


def test_covered_unknown_delivery_state_defaults_to_process():
    # can't prove it passed → not drift
    assert classify_gap("sentinel_uptime")["verdict"] == "process"


# ── uncovered classes: a candidate is born ──
def test_uncovered_class_drafts_a_candidate():
    for cls in ("sentinel_indexability", "watchdog_thirdparty", "ads_dead_destination"):
        r = classify_gap(cls)
        assert r["verdict"] == "uncovered"
        c = r["candidate"]
        assert c["proposed_wording" if "proposed_wording" in c else "wording"]  # wording present
        assert "check_key" in c and "machine_verifiable" in c


def test_indexability_candidate_wording_and_machine_verifiable():
    c = classify_gap("sentinel_indexability")["candidate"]
    assert "indexability" in c["wording"].lower()
    assert c["machine_verifiable"] is True and c["check_key"] == "indexability_ok"


def test_thirdparty_candidate_is_not_machine_verifiable():
    c = classify_gap("watchdog_thirdparty")["candidate"]
    assert c["machine_verifiable"] is False


def test_unknown_class_is_a_noop():
    assert classify_gap("something_new")["verdict"] == "unknown_class"


def test_map_version_stamped():
    assert classify_gap("sentinel_uptime")["map_version"] == FLYWHEEL_MAP_VERSION


# ── absorption on promotion ──
def test_absorption_activates_existing_battery_key():
    assert absorption_outcome("ssl_valid", machine_verifiable=True) == "activated"


def test_absorption_unimplemented_for_machine_verifiable_without_a_key():
    # indexability_ok / ad_destinations_live are NOT battery keys yet
    assert absorption_outcome("indexability_ok", machine_verifiable=True) == "promoted_unimplemented"
    assert absorption_outcome("ad_destinations_live", machine_verifiable=True) == "promoted_unimplemented"


def test_absorption_manual_when_not_machine_verifiable():
    assert absorption_outcome("thirdparty_health", machine_verifiable=False) == "manual"


# ── mapping integrity ──
def test_every_candidate_template_maps_to_an_uncovered_class():
    for cls in CANDIDATE_TEMPLATES:
        assert COVERAGE.get(cls) == ()   # candidate classes must be uncovered
