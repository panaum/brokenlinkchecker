"""Pure, I/O-free shaping for cross-app PRESENCE (Seam 3).

Presence answers one question for the OTHER app: "is there anything about this
site's production life that the person looking at the delivery record should
know right now?" It is deliberately narrow — only attention-worthy facts
appear. A healthy site yields ZERO signals, and the consumer renders nothing
at all. There is no "all good" state by design: quiet is the default, and a
strip that is usually empty is a strip people actually read when it isn't.

No DB, no network, no clock of its own — everything is passed in, so every
state is unit-testable.
"""

# Escalation tiers that earn a line. 'notice' (30-day horizon) deliberately does
# NOT: it is a calendar entry, not a thing to interrupt a QA sign-off with.
ATTENTION = ("critical", "warn")

_RANK = {"critical": 0, "warn": 1}


def _days_phrase(noun, days):
    """'SSL expires in 3 days' / 'SSL has expired' — never 'expires in -2 days'."""
    if days is None:
        return f"{noun} expiry unknown"
    if days <= 0:
        return f"{noun} has expired"
    return f"{noun} expires in {days} day{'' if days == 1 else 's'}"


def _card_text(card):
    """One human line per unhealthy sentinel card. Unknown keys fall back to the
    card's own label/fact, so a NEW sentinel check surfaces here for free."""
    key = card.get("key")
    days = card.get("days")
    if key == "ssl":
        return _days_phrase("SSL certificate", days)
    if key == "domain":
        return _days_phrase("Domain registration", days)
    if key == "index":
        return "Search visibility at risk"
    if key == "uptime":
        return "Site is not responding"
    label = card.get("label") or key or "Check"
    fact = card.get("fact")
    return f"{label}: {fact}" if fact else str(label)


def open_incident_count(incidents):
    """An incident is OPEN while it has no restored_at. `incidents` is whatever
    database.list_incidents returned (may be None)."""
    return sum(1 for i in (incidents or []) if not i.get("restored_at"))


def presence_signals(sentinel, incidents, site_path=None):
    """Most-urgent-first signals for one site. Pure.

    `sentinel` is a sentinel.summarize_sentinel payload (cards/worst/down/…);
    `incidents` is a database.list_incidents list. Returns [] when nothing needs
    attention — the consumer then renders nothing.
    """
    sentinel = sentinel or {}
    signals = []

    n_open = open_incident_count(incidents)
    if n_open:
        signals.append({
            "key": "incident",
            "severity": "critical",
            "text": f"{n_open} open incident{'' if n_open == 1 else 's'}",
            # The qualifier names WHERE this is being watched, so the reader
            # knows a human system already has it.
            "qualifier": "disaster sentinel",
            "deep_link_path": site_path,
        })

    # An uptime card already says "down"; when an incident line is present that
    # would be the same fact twice. Incidents win — they carry duration.
    holding = "monitoring holding" if not sentinel.get("down") else "site is down"
    for card in sentinel.get("cards") or []:
        if card.get("escalation") not in ATTENTION:
            continue
        if card.get("key") == "uptime" and n_open:
            continue
        signals.append({
            "key": card.get("key"),
            "severity": card.get("escalation"),
            "text": _card_text(card),
            "qualifier": holding,
            "deep_link_path": site_path,
        })

    signals.sort(key=lambda s: _RANK.get(s["severity"], 9))
    return signals


# ═══ CLIENT CHIPS ════════════════════════════════════════════════════════════
# Four honest signals per site, never a composite. See
# docs/design-notes/presence-client-chips.md for why each chip exists and why
# `sentinel` excludes both SSL (its own chip) and uptime (an open incident IS
# the uptime verdict — counting both prints one outage twice).
#
# Presence invents NO threshold. Every state below is a verdict computed by the
# module that owns it (sentinel.escalation, sentinel.indexability_verdict,
# fragility.fragility_score), so the chips stay true as those modules evolve.

CHIP_KEYS = ("ssl", "sentinel", "incidents", "fragility")

# Worst-of ladder. `settling` sits below `notice` and above `ok`: it must never
# be why a client reads green, nor why one reads red.
STATE_ORDER = ("critical", "warn", "notice", "settling", "unknown", "ok")
_STATE_RANK = {s: i for i, s in enumerate(STATE_ORDER)}


# ── Display vocabulary ───────────────────────────────────────────────────────
# The operator-facing names for the severity ladder, best-first. This is a LABEL
# layer, not a second status system: internally the states stay
# ok/settling/notice/warn/critical, the same vocabulary sentinel and the ds-status
# CSS classes already speak (constitution rule 8).
#
# NOTE the overload: 'brittle' is ALSO a fragility band (fragility.py:124, score
# >= 60) and renders as "Brittle" in FragilityPanel. Here it means "worst chip
# state". A client can therefore read `brittle` overall while its fragility chip
# says `22 · sturdy` — different axes, same word. Flagged, not hidden.
RANKING_BEST_FIRST = ("stable", "fresh", "drifting", "fragile", "brittle")

_DISPLAY = {"ok": "stable", "settling": "fresh", "notice": "drifting",
            "warn": "fragile", "critical": "brittle", "unknown": "unknown"}


def state_label(state):
    """Operator-facing name for an internal state. Unknown stays 'unknown' — it
    is not on the stable→brittle ranking because 'we could not tell' is not a
    point on a durability scale."""
    return _DISPLAY.get(state, "unknown")


def worst_state(states):
    """The most severe of a set of states. The ONLY reduction in this pipeline —
    reversible by construction, because the worst chip is still visible as
    itself. Empty → 'unknown'."""
    known = [s for s in (states or []) if s in _STATE_RANK]
    if not known:
        return "unknown"
    return min(known, key=lambda s: _STATE_RANK[s])


def _fragility_chip(fragility):
    """Stored nightly score, or FRESH MODE.

    Fresh Mode is the window before fragility.history_gate is satisfied (60+
    days AND 8+ scans). In it the chip reads 'settling' and carries ONLY how
    long the site has been watched — never a partial score, never a provisional
    band. A number computed from too little history is worse than no number,
    because it will be quoted.
    """
    if not fragility or fragility.get("insufficient"):
        gate = (fragility or {}).get("gate") or {}
        days = gate.get("have_days")
        detail = (f"{days} day{'' if days == 1 else 's'} monitored · pattern still forming"
                  if days is not None else "Pattern still forming")
        return {"key": "fragility", "state": "settling", "label": "Fragility",
                # No score, no band, no factors — Fresh Mode leaks nothing.
                "text": "settling", "detail": detail, "fresh_mode": True}

    band = fragility.get("band")
    state = {"brittle": "critical", "sturdy": "ok"}.get(band, "notice")
    score = fragility.get("score")
    return {"key": "fragility", "state": state, "label": "Fragility",
            "text": f"{score} · {band}" if score is not None else str(band),
            # The factors rule is absolute upstream; carry them, never drop them.
            "detail": " · ".join(fragility.get("factors") or []) or None}


def aggregate_chip(key, per_site):
    """Aggregate ONE chip across a client's sites. Pure.

    `per_site` is [(site_id, site_path, chips)]. The worst state always wins —
    a red on one site of thirty is still a red, and no count of greens outvotes
    it. Mirrors the Dashboard's aggregateChip() rule for rule; the shared rules
    are documented in docs/design-notes/presence-client-chips.md and asserted
    identical by tests on both sides.
    """
    found = []
    for site_id, site_path, chips in per_site:
        chip = next((c for c in (chips or []) if c.get("key") == key), None)
        if chip:
            found.append((site_id, site_path, chip))
    if not found:
        return None

    state = worst_state([c["state"] for _, _, c in found])
    at_worst = [f for f in found if f[2]["state"] == state]
    total = len(found)

    if total == 1:
        text = found[0][2]["text"]          # one site: state its own fact
    elif state == "ok":
        text = f"ok on {total} sites"
    else:
        text = f"⚠ on {len(at_worst)} of {total} sites"

    return {"key": key, "label": found[0][2]["label"], "state": state, "text": text,
            # One implicated site → carry its detail. Several → the detail would
            # be ambiguous, so say nothing rather than something misleading.
            "detail": at_worst[0][2].get("detail") if len(at_worst) == 1 else None,
            "affected": len(at_worst), "total": total,
            "site_path": at_worst[0][1] if len(at_worst) == 1 else None}


def sites_summary(per_site):
    """Shape counts only: how many sites, and how many at each state.

    Deliberately carries NO site names and NO ids. Per-site detail is reached by
    clicking through to LinkSpy on a signed handoff, where the reader is
    authenticated — it is not smuggled into a Dashboard payload where it would
    become a second, unauthenticated copy of the registry.
    """
    by_state = {}
    for _sid, _path, chips in per_site or []:
        w = worst_state([c["state"] for c in (chips or [])])
        by_state[w] = by_state.get(w, 0) + 1
    return {"total": len(per_site or []),
            "by_state": by_state,
            # Same counts under the operator-facing names, so a consumer never
            # has to hardcode the internal vocabulary to render a breakdown.
            "by_label": {state_label(k): v for k, v in by_state.items()}}


def client_presence_chips(per_site):
    """The four aggregated chips for one client, plus its worst-of.

    `per_site` is [(site_id, site_path, chips)]. Returns None when the client
    has no sites — the consumer then renders nothing. The only reduction is
    worst-of OVER THE AGGREGATED CHIPS, so the headline can never disagree with
    the chips printed beside it.
    """
    if not per_site:
        return None
    chips = [c for c in (aggregate_chip(k, per_site) for k in CHIP_KEYS) if c]
    if not chips:
        return None
    worst = worst_state([c["state"] for c in chips])
    return {"chips": chips,
            "worst": worst,
            "worst_label": state_label(worst),
            "site_count": len(per_site),
            "sites_summary": sites_summary(per_site)}


def site_chips(status, open_incidents=0, fragility=None, now=None):
    """The four chips for ONE site. Pure.

    `status` is a sentinel_status row (or None), `open_incidents` a count,
    `fragility` a stored fragility_scores row (or None).
    """
    from sentinel import days_until, escalation, indexability_verdict

    status = status or {}
    ssl_days = days_until(status.get("ssl_expiry"), now)
    dom_days = days_until(status.get("domain_expiry"), now)
    idx = indexability_verdict(status.get("robots_ok"), status.get("meta_noindex"),
                               status.get("header_noindex"), status.get("sitemap_ok"))

    def days_text(days):
        if days is None:
            return "unknown"
        if days <= 0:
            return "expired"
        return f"{days} day{'' if days == 1 else 's'}"

    # `sentinel` = worst(domain, search visibility) — NOT ssl, NOT uptime.
    sentinel_state = worst_state([escalation(dom_days), idx["overall"]])
    sentinel_text = "ok"
    if sentinel_state != "ok":
        worse_domain = _STATE_RANK.get(escalation(dom_days), 9) <= _STATE_RANK.get(idx["overall"], 9)
        sentinel_text = f"domain {days_text(dom_days)}" if worse_domain else "search visibility"

    n = int(open_incidents or 0)
    return [
        {"key": "ssl", "state": escalation(ssl_days), "label": "SSL",
         "text": days_text(ssl_days), "detail": status.get("ssl_issuer")},
        {"key": "sentinel", "state": sentinel_state, "label": "Sentinel",
         "text": sentinel_text,
         "detail": " · ".join(c["text"] for c in idx["checks"]) or None},
        {"key": "incidents", "state": "critical" if n else "ok", "label": "Incidents",
         "text": f"{n} open" if n else "none open", "detail": None},
        _fragility_chip(fragility),
    ]
