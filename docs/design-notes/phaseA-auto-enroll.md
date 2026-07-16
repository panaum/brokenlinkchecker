# Design Note — Part A: qa.completed → monitoring auto-enroll

**Status:** proposed (autonomous — code proceeds after commit).
**Branch:** `feat/auto-enroll` (LinkSpy).
**Architecture:** v7 §4 step 4 (sign-off → monitoring auto-enrolls, default weekly,
one-click off) + §6 constitution (new behaviour behind a flag DEFAULT OFF).

## Behaviour
When the spine inbox **processes a `qa.completed` event** (already: verified,
recorded, timeline-written) AND `AUTO_ENROLL=1`:

1. Resolve the site by the event's `registry_site_id` (`get_site`). Missing → skip.
2. **Only if monitoring is currently DISABLED/unset** for that site:
   - `set_monitoring(site_id, enabled=True, freq="Weekly")` — the default cadence.
   - Write a `client_timeline` row `type="monitoring.auto_enrolled"`
     (payload `{cadence:"Weekly"}`, keyed by registry ids).
   - Slack: *"auto-enrolled {url} to weekly monitoring after QA sign-off —
     one-click revert: {link}"* (link = `{FRONTEND_URL}/dashboard/{site_id}` when
     `FRONTEND_URL` is set; omitted gracefully otherwise).
3. **Never downgrade / never touch a monitored site:** if `monitoring_enabled` is
   already truthy (e.g. an existing *daily* cadence), do nothing. The only
   transition this makes is **off → weekly**, never weekly→anything or daily→weekly.

## Idempotency
State-based, not ledger-based: the *first* `qa.completed` flips monitoring on;
every subsequent `qa.completed` for the same site finds `monitoring_enabled=True`
and skips. The timeline row + Slack fire ONLY on the actual off→weekly transition.
(The spine inbox is already idempotent per event id, so a re-delivered event is a
no-op before this even runs.)

## Flag-off = byte-identical
`AUTO_ENROLL` unset/0 → the entire block is skipped; the inbox behaves exactly as
today (snapshot-tested: `set_monitoring` is never called).

## Guardrails honoured
- No flag flip by me — `AUTO_ENROLL` ships DEFAULT OFF; the operator flips it.
- No unattended write to a QA-app row (T4): this touches only LinkSpy's own
  `sites` + `client_timeline`.
- Additive only; no migration (reuses `sites.monitoring_enabled/freq`).

## Exit tests
- pure `should_auto_enroll(flag_on, monitoring_enabled)`: (on, unmonitored)→enroll;
  (on, monitored)→skip; (off, *)→skip.
- inbox integration (monkeypatched): flag on + unmonitored → `set_monitoring`
  called `(site, True, "Weekly")` + timeline written; flag on + already monitored
  → `set_monitoring` NOT called; flag off → neither, byte-identical.
