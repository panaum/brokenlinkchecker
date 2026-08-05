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
