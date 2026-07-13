"""QA-bridge check catalog — the versioned, provenance-tagged mapping from a QA
delivery-checklist item type to a LinkSpy verification source, plus the PURE
verdict derivation for each. No I/O: a caller assembles a `snapshot` from the
LATEST STORED results and passes it here.

Verdict vocabulary (honest by construction):
  holding         — provably still passing
  failing         — a PROVABLE regression (only provable failures render as drift)
  couldnt_verify  — we watch this, but couldn't re-verify (provider blocked, or
                    the data is stale/unavailable) — NEVER shown as failing

A derivation returning None means "no signal for this item on this page" — the
check is omitted entirely. The module covers what it covers; it never emits a
"not monitored" stub for items with no machine equivalent.
"""

CATALOG_VERSION = 1

# Provenance per row: which LinkSpy subsystem proves it. This is the v1
# machine-verifiable set. Items with no machine equivalent (e.g. "Arabic fonts
# added", browser-visual checks) are deliberately absent.
CATALOG = [
    {"key": "ssl_valid",      "source": "sentinel",       "label": "SSL certificate valid"},
    {"key": "ssl_expiry",     "source": "sentinel",       "label": "SSL certificate not expiring"},
    {"key": "domain_expiry",  "source": "sentinel",       "label": "Domain registration current"},
    {"key": "uptime",         "source": "sentinel",       "label": "Site reachable"},
    {"key": "broken_links",   "source": "core_scan",      "label": "No broken links"},
    {"key": "ga4_installed",  "source": "tracking_audit", "label": "Analytics installed"},
    {"key": "gtm_setup",      "source": "tracking_audit", "label": "Tag manager present"},
    {"key": "pixel_present",  "source": "tracking_audit", "label": "Ad pixel present"},
    {"key": "page_load_time", "source": "perf_ledger",    "label": "Page load within budget"},
    {"key": "forms_submit",   "source": "form_audit",     "label": "Forms working"},
]
CATALOG_KEYS = [c["key"] for c in CATALOG]
_LABEL = {c["key"]: c["label"] for c in CATALOG}
_SOURCE = {c["key"]: c["source"] for c in CATALOG}

HOLDING, FAILING, COULDNT = "holding", "failing", "couldnt_verify"

# A regression is only "provable" when the load time is both meaningfully slower
# than its own baseline AND above an absolute floor — so tiny jitter never trips.
PERF_REGRESSION_FACTOR = 1.5
PERF_MIN_MS = 2500

# The tracking types this catalog knows how to prove, and the catalog key each
# maps to. (Detection lives in the snapshot; this only names the mapping.)
_TRACK_KEYS = {"ga4": "ga4_installed", "gtm": "gtm_setup", "pixel": "pixel_present"}
_TRACK_NOUN = {"ga4_installed": "Analytics", "gtm_setup": "Tag manager", "pixel_present": "Ad pixel"}


def _days_until(expiry, now=None):
    """Whole calendar days until `expiry` (ISO/aware). None if unknown. Mirrors
    sentinel.days_until so the two agree; kept local to keep this module pure."""
    from datetime import datetime, timezone
    if not expiry:
        return None
    try:
        d = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
        d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None
    base = now or datetime.now(timezone.utc)
    return int((d - base).total_seconds() // 86400)


def _check(key, verdict, detail, last_checked=None, incident_ref=None):
    return {"key": key, "source": _SOURCE.get(key), "label": _LABEL.get(key),
            "verdict": verdict, "detail_plain": detail,
            "last_checked": last_checked, "incident_ref": incident_ref}


# ── per-source derivations (each returns a check dict, or None to omit) ──
def _ssl_valid(sn):
    s = sn.get("sentinel") or {}
    exp = s.get("ssl_expiry")
    lc = s.get("last_checked_at")
    if not exp:
        return _check("ssl_valid", COULDNT, "Couldn't read the SSL certificate this check.", lc)
    days = _days_until(exp, sn.get("_now"))
    if days is not None and days < 0:
        return _check("ssl_valid", FAILING, "SSL certificate has expired.", lc)
    return _check("ssl_valid", HOLDING, "SSL certificate is valid.", lc)


def _ssl_expiry(sn):
    s = sn.get("sentinel") or {}
    exp = s.get("ssl_expiry")
    lc = s.get("last_checked_at")
    if not exp:
        return None                        # validity already covered; no countdown to show
    days = _days_until(exp, sn.get("_now"))
    if days is None:
        return None
    if days < 0:
        return _check("ssl_expiry", FAILING, "SSL certificate has expired.", lc)
    if days <= 14:
        return _check("ssl_expiry", FAILING, f"SSL certificate expires in {days} days.", lc)
    return _check("ssl_expiry", HOLDING, f"SSL valid · {days} days remaining.", lc)


def _domain_expiry(sn):
    s = sn.get("sentinel") or {}
    exp = s.get("domain_expiry")
    lc = s.get("last_checked_at")
    if not exp:
        return None
    days = _days_until(exp, sn.get("_now"))
    if days is None:
        return None
    if days < 0:
        return _check("domain_expiry", FAILING, "Domain registration has lapsed.", lc)
    if days <= 30:
        return _check("domain_expiry", FAILING, f"Domain registration expires in {days} days.", lc)
    return _check("domain_expiry", HOLDING, f"Domain registered · {days} days remaining.", lc)


def _uptime(sn):
    u = sn.get("uptime") or {}
    lc = u.get("last_checked_at")
    if not u.get("has_pings"):
        return _check("uptime", COULDNT, "No uptime samples recorded yet.", lc)
    if u.get("down"):
        return _check("uptime", FAILING, "Site is not responding.", lc, sn.get("incident_ref"))
    pct = u.get("pct")
    detail = f"Reachable · {pct}% uptime" if pct is not None else "Reachable."
    return _check("uptime", HOLDING, detail, lc)


def _broken_links(sn):
    sc = sn.get("scan") or {}
    if not sc.get("has_scan"):
        return _check("broken_links", COULDNT, "No scan on record yet.", None)
    n = sc.get("broken_on_page")
    lc = sc.get("scanned_at")
    if n is None:
        return _check("broken_links", COULDNT, "This page wasn't in the latest scan.", lc)
    if n > 0:
        return _check("broken_links", FAILING, f"{n} broken link{'s' if n != 1 else ''} on this page.", lc)
    return _check("broken_links", HOLDING, "No broken links on this page.", lc)


def _tracking(sn, key):
    t = sn.get("tracking") or {}
    exp = sn.get("expected_tracking") or {}
    lc = (sn.get("scan") or {}).get("scanned_at")
    tk = next(k for k, v in _TRACK_KEYS.items() if v == key)   # ga4/gtm/pixel
    det = t.get(tk)
    noun = _TRACK_NOUN[key]
    expected = bool(exp.get(tk))
    if not det:
        if expected:
            return _check(key, FAILING, f"{noun} was expected but not detected on this page.", lc)
        return None                        # not detected, not expected → nothing to say
    if det.get("healthy") is False:
        return _check(key, FAILING, f"{noun} is present but not loading correctly.", lc)
    if det.get("healthy") is None:
        return _check(key, COULDNT, f"{noun} detected; couldn't confirm it's loading.", lc)
    tag_id = det.get("id")
    return _check(key, HOLDING, f"{noun} detected and healthy" + (f" · {tag_id}." if tag_id else "."), lc)


def _page_load_time(sn):
    p = sn.get("perf") or {}
    cur = p.get("current_p50")
    lc = p.get("scanned_at")
    if cur is None:
        return _check("page_load_time", COULDNT, "No performance sample on record yet.", lc)
    base = p.get("baseline_p50")
    cur_s = f"{cur / 1000:.1f}s"
    if base and cur > base * PERF_REGRESSION_FACTOR and cur > PERF_MIN_MS:
        return _check("page_load_time", FAILING,
                      f"Median load time regressed to {cur_s} (baseline {base / 1000:.1f}s).", lc)
    if base:
        return _check("page_load_time", HOLDING, f"Median load {cur_s} (baseline {base / 1000:.1f}s).", lc)
    return _check("page_load_time", HOLDING, f"Median load {cur_s}.", lc)


def _forms_submit(sn):
    sc = sn.get("scan") or {}
    tr = sn.get("tracer") or {}
    forms = sc.get("forms") or []
    enrolled = bool(tr.get("enrolled"))
    verdict = tr.get("verdict")
    lc = tr.get("last_run_at") or sc.get("scanned_at")
    # A verified-delivery failure is the strongest signal.
    if verdict == "failed":
        return _check("forms_submit", FAILING, "A verified-delivery test failed on this form.", lc)
    if not forms and not enrolled:
        return None                        # no form here and none enrolled → omit
    broken = [f for f in forms if not f.get("intact")]
    if broken:
        return _check("forms_submit", FAILING,
                      f"{len(broken)} form{'s' if len(broken) != 1 else ''} on this page is broken.", lc)
    if enrolled and verdict == "verified":
        return _check("forms_submit", HOLDING, "Form working — delivery verified end-to-end.", lc)
    if forms:
        return _check("forms_submit", HOLDING, "Form present and structurally intact.", lc)
    # enrolled but no run yet and no structural form on the page
    return _check("forms_submit", COULDNT, "Enrolled for delivery testing; no run yet.", lc)


_DERIVERS = {
    "ssl_valid": _ssl_valid,
    "ssl_expiry": _ssl_expiry,
    "domain_expiry": _domain_expiry,
    "uptime": _uptime,
    "broken_links": _broken_links,
    "ga4_installed": lambda sn: _tracking(sn, "ga4_installed"),
    "gtm_setup": lambda sn: _tracking(sn, "gtm_setup"),
    "pixel_present": lambda sn: _tracking(sn, "pixel_present"),
    "page_load_time": _page_load_time,
    "forms_submit": _forms_submit,
}


def derive_checks(snapshot):
    """Run every catalog deriver over `snapshot`; drop the None (not-applicable)
    ones. Order follows CATALOG. Deterministic and pure."""
    out = []
    for c in CATALOG:
        try:
            res = _DERIVERS[c["key"]](snapshot)
        except Exception:
            res = None                     # a malformed source never breaks the whole payload
        if res is not None:
            out.append(res)
    return out


def summarize(checks):
    """Roll a check list into the counts the QA header needs."""
    holding = sum(1 for c in checks if c["verdict"] == HOLDING)
    failing = sum(1 for c in checks if c["verdict"] == FAILING)
    couldnt = sum(1 for c in checks if c["verdict"] == COULDNT)
    return {"total": len(checks), "holding": holding, "failing": failing,
            "couldnt_verify": couldnt}
