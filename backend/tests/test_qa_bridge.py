"""QA-bridge PR1 — catalog verdict derivation (honest mapping), service-key
parsing + hashing, the rate limiter, and a guard that the status path can NEVER
trigger a scan/probe."""
import inspect
from datetime import datetime, timezone, timedelta

from qa_catalog import (derive_checks, summarize, CATALOG, CATALOG_KEYS,
                        HOLDING, FAILING, COULDNT)
from qa_bridge import parse_service_key, RateLimiter


def _iso(days_from_now):
    return (datetime.now(timezone.utc) + timedelta(days=days_from_now)).isoformat()


def _by_key(checks):
    return {c["key"]: c for c in checks}


# ── catalog shape ──
def test_catalog_is_versioned_with_provenance():
    for row in CATALOG:
        assert row["key"] and row["source"] and row["label"]
    assert len(set(CATALOG_KEYS)) == len(CATALOG_KEYS)     # keys unique


# ── SSL / domain countdowns ──
def test_ssl_holding_when_comfortable_and_failing_when_near_or_expired():
    s = _by_key(derive_checks({"sentinel": {"ssl_expiry": _iso(200), "last_checked_at": _iso(0)}}))
    assert s["ssl_valid"]["verdict"] == HOLDING
    assert s["ssl_expiry"]["verdict"] == HOLDING and "remaining" in s["ssl_expiry"]["detail_plain"]

    near = _by_key(derive_checks({"sentinel": {"ssl_expiry": _iso(6), "last_checked_at": _iso(0)}}))
    assert near["ssl_expiry"]["verdict"] == FAILING and "expires in" in near["ssl_expiry"]["detail_plain"]

    expired = _by_key(derive_checks({"sentinel": {"ssl_expiry": _iso(-2)}}))
    assert expired["ssl_valid"]["verdict"] == FAILING
    assert expired["ssl_expiry"]["verdict"] == FAILING


def test_ssl_unreadable_is_couldnt_verify_never_failing():
    s = _by_key(derive_checks({"sentinel": {"ssl_expiry": None, "last_checked_at": _iso(0)}}))
    assert s["ssl_valid"]["verdict"] == COULDNT            # unverifiable ≠ failing
    assert "ssl_expiry" not in s                            # no countdown to show → omitted


def test_domain_expiry_bands():
    hold = _by_key(derive_checks({"sentinel": {"domain_expiry": _iso(120)}}))
    assert hold["domain_expiry"]["verdict"] == HOLDING
    fail = _by_key(derive_checks({"sentinel": {"domain_expiry": _iso(10)}}))
    assert fail["domain_expiry"]["verdict"] == FAILING


# ── uptime ──
def test_uptime_holding_failing_and_couldnt():
    up = _by_key(derive_checks({"uptime": {"has_pings": True, "down": False, "pct": 99.9}}))
    assert up["uptime"]["verdict"] == HOLDING and "99.9" in up["uptime"]["detail_plain"]

    down = _by_key(derive_checks({"uptime": {"has_pings": True, "down": True, "pct": 80.0},
                                  "incident_ref": "inc-123"}))
    assert down["uptime"]["verdict"] == FAILING
    assert down["uptime"]["incident_ref"] == "inc-123"      # links to the incident

    none = _by_key(derive_checks({"uptime": {"has_pings": False}}))
    assert none["uptime"]["verdict"] == COULDNT


# ── broken links ──
def test_broken_links_from_scan():
    clean = _by_key(derive_checks({"scan": {"has_scan": True, "broken_on_page": 0, "scanned_at": _iso(0)}}))
    assert clean["broken_links"]["verdict"] == HOLDING
    dirty = _by_key(derive_checks({"scan": {"has_scan": True, "broken_on_page": 3, "scanned_at": _iso(0)}}))
    assert dirty["broken_links"]["verdict"] == FAILING and "3 broken" in dirty["broken_links"]["detail_plain"]
    nomap = _by_key(derive_checks({"scan": {"has_scan": True, "broken_on_page": None}}))
    assert nomap["broken_links"]["verdict"] == COULDNT


# ── tracking: detected/expected/unhealthy/unknown ──
def test_tracking_detected_healthy_is_holding_with_id():
    s = _by_key(derive_checks({"tracking": {"ga4": {"present": True, "healthy": True, "id": "G-ABC123"}}}))
    assert s["ga4_installed"]["verdict"] == HOLDING and "G-ABC123" in s["ga4_installed"]["detail_plain"]


def test_tracking_expected_but_missing_is_failing():
    s = _by_key(derive_checks({"tracking": {}, "expected_tracking": {"ga4": True}}))
    assert s["ga4_installed"]["verdict"] == FAILING


def test_tracking_absent_and_not_expected_is_omitted():
    checks = derive_checks({"tracking": {}, "expected_tracking": {}})
    assert "ga4_installed" not in _by_key(checks)           # no stub / no noise


def test_tracking_unknown_health_is_couldnt_verify():
    s = _by_key(derive_checks({"tracking": {"pixel": {"present": True, "healthy": None, "id": None}}}))
    assert s["pixel_present"]["verdict"] == COULDNT


# ── perf regression vs baseline ──
def test_perf_regression_is_failing_only_when_meaningful():
    reg = _by_key(derive_checks({"perf": {"current_p50": 6000, "baseline_p50": 1500, "scanned_at": _iso(0)}}))
    assert reg["page_load_time"]["verdict"] == FAILING

    steady = _by_key(derive_checks({"perf": {"current_p50": 1600, "baseline_p50": 1500}}))
    assert steady["page_load_time"]["verdict"] == HOLDING

    # slower but under the absolute floor → not flagged (jitter, not regression)
    tiny = _by_key(derive_checks({"perf": {"current_p50": 900, "baseline_p50": 400}}))
    assert tiny["page_load_time"]["verdict"] == HOLDING

    none = _by_key(derive_checks({"perf": {"current_p50": None}}))
    assert none["page_load_time"]["verdict"] == COULDNT


# ── forms: structural vs delivery-verified vs omitted ──
def test_forms_structural_and_delivery_and_omit():
    intact = _by_key(derive_checks({"scan": {"forms": [{"intact": True}]}}))
    assert intact["forms_submit"]["verdict"] == HOLDING

    broken = _by_key(derive_checks({"scan": {"forms": [{"intact": False}]}}))
    assert broken["forms_submit"]["verdict"] == FAILING

    verified = _by_key(derive_checks({"scan": {"forms": [{"intact": True}]},
                                      "tracer": {"enrolled": True, "verdict": "verified"}}))
    assert verified["forms_submit"]["verdict"] == HOLDING and "delivery verified" in verified["forms_submit"]["detail_plain"].lower()

    failed = _by_key(derive_checks({"tracer": {"enrolled": True, "verdict": "failed"}}))
    assert failed["forms_submit"]["verdict"] == FAILING

    # no form on the page and not enrolled → nothing to say
    assert "forms_submit" not in _by_key(derive_checks({"scan": {"forms": []}}))


# ── summarize + robustness ──
def test_summarize_counts():
    checks = derive_checks({"sentinel": {"ssl_expiry": _iso(200)},
                            "uptime": {"has_pings": True, "down": True},
                            "scan": {"has_scan": True, "broken_on_page": 0}})
    s = summarize(checks)
    assert s["total"] == len(checks) and s["failing"] >= 1 and s["holding"] >= 1


def test_derive_never_raises_on_garbage():
    assert derive_checks({}) == derive_checks({}) is not None
    assert isinstance(derive_checks({"sentinel": "not-a-dict", "scan": 42}), list)


# ── service-key parsing ──
def test_parse_service_key_bearer_and_header_and_absent():
    assert parse_service_key(authorization="Bearer qab_tok123") == "qab_tok123"
    assert parse_service_key(authorization="bearer qab_low") == "qab_low"
    assert parse_service_key(x_api_key="qab_via_header") == "qab_via_header"
    assert parse_service_key() is None
    assert parse_service_key(authorization="Basic nope") is None


def test_key_hash_is_stable_sha256_and_not_reversible():
    from database import _qa_hash
    h = _qa_hash("qab_secret")
    assert h == _qa_hash("qab_secret") and len(h) == 64 and "qab_secret" not in h


# ── rate limiter ──
def test_rate_limiter_allows_then_blocks_then_resets():
    rl = RateLimiter(max_requests=3, window_s=60.0)
    assert [rl.allow("k", 0.0) for _ in range(3)] == [True, True, True]
    assert rl.allow("k", 1.0) is False                      # 4th within window blocked
    assert rl.allow("k", 61.0) is True                       # window rolled over
    assert rl.allow("other", 1.0) is True                    # per-key isolation


# ── the critical guarantee: status path triggers no scans/probes ──
def test_snapshot_assembler_triggers_no_scans_or_probes():
    import database
    src = inspect.getsource(database._qa_snapshot_sync)
    forbidden = ("run_scan", "scan_site", "_insert_scan", "add_uptime_ping",
                 "run_sentinel_for_site", "run_uptime_for_site", "upsert_perf_snapshot",
                 "check_ssl", "check_domain_expiry", "run_consent", "insert_tracer_run",
                 "execute_tracer")
    for name in forbidden:
        assert name not in src, f"snapshot must not call {name} (no scans from the status path)"
