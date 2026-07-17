"""The Quality Flywheel — DETERMINISTIC gap classifier (Phase 5, LinkSpy).

Rule-based, NO LLM (constitution). Given a resolved incident's class and whether
the covering battery check passed at delivery, decide: drift (covered, passed) /
process (covered, missed) / uncovered (→ draft a checklist candidate).

Versioned with provenance: FLYWHEEL_MAP_VERSION + a comment on every row saying
why it exists and what battery key covers it. Nothing here is keyed to an
individual developer (constitution rule 10).
"""

FLYWHEEL_MAP_VERSION = 1

# incident_class → the battery check key(s) that would have caught it.
# Empty tuple = NOT COVERED by the current battery → a candidate is born.
COVERAGE = {
    "finding_broken":        ("broken_links",),           # a broken link at delivery
    "finding_dead_cta":      ("broken_links",),            # a dead CTA is a broken destination
    "finding_unverifiable":  ("broken_links",),            # best-effort: same probe
    "sentinel_ssl":          ("ssl_valid", "ssl_expiry"),  # cert validity + countdown
    "sentinel_domain":       ("domain_expiry",),           # registration countdown
    "sentinel_uptime":       ("uptime",),                  # reachability
    "perf_regression":       ("page_load_time",),          # perf ledger p50
    "tracking_missing":      ("ga4_installed", "gtm_setup", "pixel_present"),
    "forms_broken":          ("forms_submit",),
    # ── uncovered classes (no battery key) → candidates ──
    "sentinel_indexability": (),                           # robots/noindex/sitemap
    "watchdog_thirdparty":   (),                           # third-party embed outage
    "ads_dead_destination":  (),                           # live ad → dead page
}

# Uncovered class → the proposed candidate. `machine_verifiable` reflects whether
# LinkSpy COULD probe it (sentinel/ads-guard already do) — but since none of these
# are battery catalog keys yet, promotion lands as 'promoted_unimplemented'
# (never auto-builds a probe).
CANDIDATE_TEMPLATES = {
    "sentinel_indexability": {
        "check_key": "indexability_ok",
        "wording": "Search-engine indexability (robots.txt / noindex / sitemap) re-verified at launch",
        "machine_verifiable": True,
    },
    "watchdog_thirdparty": {
        "check_key": "thirdparty_health",
        "wording": "Critical third-party embeds (chat, pixels, widgets) confirmed loading at launch",
        "machine_verifiable": False,
    },
    "ads_dead_destination": {
        "check_key": "ad_destinations_live",
        "wording": "Live ad destinations verified reachable at launch",
        "machine_verifiable": True,
    },
}

# The battery keys that actually exist today (for absorption: existing vs unimplemented).
BATTERY_KEYS = frozenset({
    "ssl_valid", "ssl_expiry", "domain_expiry", "uptime", "broken_links",
    "ga4_installed", "gtm_setup", "pixel_present", "page_load_time", "forms_submit",
})


def classify_gap(incident_class, covered_passed_at_delivery=None):
    """Pure verdict. `covered_passed_at_delivery`: True (passed) / False (NA or
    failed) / None (unknown → treated as missed, since we can't prove it passed).

    Returns one of:
      {"verdict": "unknown_class"}                      — class not in the map
      {"verdict": "drift", "covered_by": (...)}         — covered + passed → no candidate
      {"verdict": "process", "covered_by": (...)}       — covered + missed → note only
      {"verdict": "uncovered", "candidate": {...} }     — draft a checklist candidate
    """
    keys = COVERAGE.get(incident_class)
    if keys is None:
        return {"verdict": "unknown_class", "map_version": FLYWHEEL_MAP_VERSION}
    if not keys:
        return {"verdict": "uncovered", "map_version": FLYWHEEL_MAP_VERSION,
                "candidate": dict(CANDIDATE_TEMPLATES.get(incident_class, {}))}
    verdict = "drift" if covered_passed_at_delivery is True else "process"
    return {"verdict": verdict, "map_version": FLYWHEEL_MAP_VERSION, "covered_by": keys}


def absorption_outcome(check_key, machine_verifiable):
    """On checklist.item_promoted: decide how LinkSpy absorbs it.
      - not machine_verifiable → 'manual' (no catalog change)
      - machine_verifiable + existing battery key → 'activated'
      - machine_verifiable + no existing key → 'promoted_unimplemented' (Slack;
        NEVER auto-build a probe)
    """
    if not machine_verifiable:
        return "manual"
    return "activated" if check_key in BATTERY_KEYS else "promoted_unimplemented"
