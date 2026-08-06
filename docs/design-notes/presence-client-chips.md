# Client presence — four chips, no composite

**Date:** 2026-08-05 · **Branches:** `feat/presence-linkspy` · `feat/presence-dashboard`
· **Flag:** `PRESENCE=1` (the same two flags as the page-level strip; no third).

Extends cross-app presence from the page checklist up to the **client** level.
The rule that shapes everything below: **surface the actual signals, never an
invented composite.** Four honest chips teach the team what "healthy" means; a
single amber verdict tells them nothing and cannot be acted on.

Prior art in this repo: [`presence-cross-app.md`](./presence-cross-app.md).

---

## 1. The one place aggregation is allowed

There is exactly one reduction in this pipeline, and it is `max()` over a
severity ladder — never a weighted blend:

```
critical > warn > notice > settling/unknown > ok
```

`max()` is used for (a) the leading emoji on the detail line and (b) the single
dot on the client list. It is honest because it is reversible: the worst chip is
still visible as itself one click away, and nothing is averaged into a number
that no longer names its cause.

**Explicitly not built:** any 0–100 "client health score", any weighted roll-up,
any bucketing of four chips into one word. If a future surface wants one, it
needs an ADR — that is a change to what the platform claims, not an extension.

## 2. The four chips

| Chip | Source | Why it is its own chip |
|---|---|---|
| **SSL** | `sentinel_status.ssl_expiry` → `days_until` → `escalation` | A dated, actionable countdown with a known owner. Never blended with anything. |
| **Sentinel** | worst of **domain expiry** + **search visibility** | The rest of the disaster sentinel — the checks that silently delete a site from the world. |
| **Open incidents** | `sentinel_incidents` where `restored_at IS NULL` | Present-tense downtime. The only chip about *now* rather than *soon*. |
| **Fragility** | stored `fragility_scores` row (nightly) | Longitudinal: does this client's work keep breaking? The only chip with memory. |

### Why "sentinel" excludes SSL *and* uptime

SSL is a sentinel check, and so is uptime — but a chip that repeats what the
chip beside it already said is noise dressed as information:

- **SSL** gets its own chip because it is the most common and most fixable of
  the four sentinel checks. Leaving it inside a rolled-up "sentinel" chip would
  have hidden the single most actionable date on the page.
- **Uptime** is deliberately *absent* from the sentinel chip, because an open
  incident **is** the uptime verdict. `sentinel.py` opens an incident after two
  consecutive failed pings — the incident row is the materialisation of
  `downtime_state()`. Counting both would print the same outage twice with two
  different colours.

So: **sentinel chip = worst(domain, search visibility)**. Documented here
because the name does not say so on its own.

A useful consequence: presence never reads `uptime_pings`. The whole client
surface is three bulk queries — `sentinel_status`, open `sentinel_incidents`,
`fragility_scores` — regardless of how many sites a client has.

### Thresholds (all inherited, none invented)

| Chip | critical | warn | notice | ok | unknown |
|---|---|---|---|---|---|
| SSL | ≤ 3 days | ≤ 14 days | ≤ 30 days | > 30 days | no expiry recorded |
| Sentinel — domain | ≤ 3 days | ≤ 14 days | ≤ 30 days | > 30 days | not recorded |
| Sentinel — visibility | robots blocking, or `noindex` | — | sitemap missing/unparseable | indexable | not checked |
| Open incidents | ≥ 1 open | — | — | 0 open | — |
| Fragility | band `brittle` (score ≥ 60) | — | band `normal` (26–59) | band `sturdy` (≤ 25) | — |

SSL/domain ladders are `sentinel.LADDER = (30, 14, 3)`, unchanged. Visibility is
`indexability_verdict()`, unchanged. Fragility bands are `fragility_score()`,
unchanged. **Presence invents no threshold of its own** — it is a renderer of
verdicts other modules already own, which is the only way the chips can stay
true when those modules evolve.

`normal` maps to **notice**, not warn, on purpose: `normal` is the middle 34
points of the band range and describes most healthy sites. Painting the median
amber would train the team to ignore amber.

### Fresh sites — "settling", never a score

`fragility.history_gate` already refuses to score a site with fewer than **60
days** and **8 scans** of history: *"a score without reasons is astrology."* The
chip honours that gate rather than working around it — it reads **`settling`**,
in neutral grey, with a hover tooltip naming what is still missing
(`Needs 60+ days and 8+ scans of history — 34 days, 5 scans so far`).

`settling` is not a bad state and not a good one. It ranks below `notice` and
above `ok` in the worst-of ladder — it must never be the reason a client shows
green, and must never be the reason one shows red.

## 3. Multi-site clients

A Dashboard client maps to N LinkSpy sites (distinct `Page.registrySiteId`
across its projects). Each chip aggregates across those sites **independently**:

- **state** = the worst state across the client's sites, per chip.
- **never** hide a red because most sites are green — asserted by test.
- **text** carries the count when it is not unanimous:

| Sites | All ok | Some not ok |
|---|---|---|
| 1 | `SSL 47 days` | `SSL 3 days` |
| N | `SSL ok on 3 sites` | `SSL ⚠ on 1 of 3 sites` |

Each chip aggregates on its own axis, so one site's SSL problem and another's
fragility problem both show — they are not collapsed into "2 sites have
issues". The chips stay orthogonal all the way up.

**Keyed on site ids, not client ids.** The Dashboard asks about the sites it
actually knows (`Page.registrySiteId`), not `Client.registryClientId` — the
former is set per-deliverable during real work, the latter may still be null on
a client whose pages are fully linked. Asking with what you know avoids a whole
class of "linked but invisible".

## 4. Rendering

**Client detail** (`/dashboard/clients/[clientId]`) — one line under the header:

```
🔴 Northbeam · SSL ⚠ on 1 of 3 sites · Sentinel ok on 3 sites · 1 open incident · Fragility settling
```

Chip colour reflects **that chip's own state**, not the line's worst. The
leading emoji is the worst-of. Server-rendered; each chip links into LinkSpy via
a signed handoff when exactly one site is implicated.

**Client list** (`/dashboard/clients`) — one dot per card, coloured by worst
chip, with the worst chip's text as its tooltip. Fetched client-side after
paint so the directory never waits on LinkSpy.

**Unmapped clients render nothing** — no dot, no line, no reserved space. A
client with no linked site is byte-identical to today.

### A deliberate departure from the page-level strip

The checklist strip renders **nothing** when all is well; this line renders
**four green chips**. That is not an inconsistency, it is a different job:

- The checklist strip is an **interruption** during focused work. Absence is the
  message; an "all good" band would be noise a tester learns to skip.
- The client line is a **status board**. You arrived asking "how is this client
  doing" — "everything is green, and here is what green means" is the answer to
  the question actually being asked, and it is what teaches the four signals.

## 5. Caching and failure

| Layer | Window | Behaviour |
|---|---|---|
| LinkSpy endpoint | **5 min** per site id, in-process + `Cache-Control: private, max-age=300` | A cold client page costs 3 bulk queries; every page in the next 5 minutes costs none |
| Dashboard fetch | **60 s** | Independent of the edge window, so a stale edge answer still refreshes promptly |

Staleness over errors (constitution rule 6): unreachable → last-known-good,
marked stale; no cache → render nothing at all on both surfaces. Neither page
ever blocks, errors, or shifts layout waiting for presence.

**No silent caps:** the endpoint accepts at most **250** site ids per request. A
longer list is truncated *and says so* (`truncated: true` + the count dropped),
which the Dashboard logs server-side. A cap that lies about coverage is worse
than no cap.

## 6. Client linking — link 3–5 real clients, not all 89

The chips only appear for a client whose `Client.registryClientId` is set. That
annotation is created by a human pressing **"Link to LinkSpy"** on one client at
a time. There is deliberately **no bulk linking path** — not in the endpoint,
not in the action, not behind a flag — and a test on each side asserts one
cannot appear by accident.

**Link 3–5 real clients before rollout. Do not sweep all 89.** The reasons, in
order of how much they will cost you:

1. **Registry ids are eternal (§8.2).** Linking either claims an existing
   registry client or mints a new one. A wrong link is not a display bug — it is
   a permanent id that events, ledgers and the timeline will reference. Merging
   two clients later means a `merged_into` pointer, never a delete.
2. **A bulk sweep would create 89 registry clients by name-match**, and the
   Dashboard's client list is known to be deliverable-shaped ("Build | Funnel 2
   LP" — §2 Seam 1). Most of those entries are not clients at all. Sweeping them
   would fill the registry with garbage that is expensive to remove and cheap to
   avoid.
3. **The chips need something to say.** A freshly linked client with no LinkSpy
   sites renders four `unknown` chips, and one with new sites sits in Fresh Mode
   for 60 days. Linking five clients that already have monitored, mature sites
   is the only way to see whether the surface is actually useful.

Pick clients that are (a) unambiguously real clients, (b) already have sites in
LinkSpy, and (c) have been monitored long enough to be past the fragility gate —
so at least one link shows a real fragility band rather than `settling`.

Once those five have lived on the surface for a week, decide whether to keep
linking by hand or to build a reviewed mapping UI (the §2 Seam 1 hygiene pass,
which is exactly this problem at 89× scale and was deliberately deferred).

## 7. Names and activation runbook

The feature is **client presence chips**. The flag is **`PRESENCE_CHIPS`**. The
read endpoint is **`/api/registry-bridge/client-presence`**. That naming is the
honest one: this surface renders presence signals as chips — it does not perform
analysis, and calling it "intelligence" oversold it.

Both sides now speak this contract:

| | LinkSpy (serves) | Dashboard (calls) |
|---|---|---|
| read | `GET /api/registry-bridge/client-presence?registry_client_id=` | `client-presence-chips.ts` |
| link | `POST /api/registry-bridge/link-client` | `link-actions.ts` |
| flag | `PRESENCE_CHIPS=1` | `PRESENCE_CHIPS=1` |

Responses, so the runbook's checks are unambiguous:

| Situation | Response |
|---|---|
| flag off | `404 {"error":"presence_chips_disabled"}` — indistinguishable from the route not existing |
| flag on, client unknown or has no sites | `200 {"chips":[], "site_count":0, ...}` — a valid empty answer |
| flag on, client has sites | `200` with four aggregated chips + `sites_summary` |
| storage fault | `503 {"error":"presence_chips_unavailable"}` — **a real fault, not the off state** |

### Env vars, exact placement

| Surface | Var | Value |
|---|---|---|
| Vercel `dashboard` | `PRESENCE_CHIPS` | `1` |
| Railway (LinkSpy backend) | `PRESENCE_CHIPS` | `1` *(after the rename above; today it is still `CLIENT_INTELLIGENCE`)* |

No new secrets. Both sides reuse `LINKSPY_API_URL` / `LINKSPY_API_KEY`.
`PRESENCE` (the page-level presence flag) is independent and may stay off.

### Order of operations

1. **Deploy both branches.** Nothing changes — both flags unset.
2. **Rename the LinkSpy side** per the table above, then set `PRESENCE_CHIPS=1`
   on Railway. Verify:
   ```bash
   curl -s -H "Authorization: Bearer $LINKSPY_API_KEY" \
     "$LINKSPY_API_URL/api/registry-bridge/client-presence?registry_client_id=00000000-0000-0000-0000-000000000000"
   # expect 200, chips: [], site_count: 0 — an unknown client is a valid empty answer, not a 404
   ```
   A 404 here means the rename has not shipped, or the flag is unset.
3. **Set `PRESENCE_CHIPS=1` on Vercel `dashboard`** and redeploy. Every client
   page now shows either four chips or the not-linked strip.
4. **Link the pilot client.** Open `/dashboard/clients/<id>` → **Link to
   LinkSpy**. Leave the id box **blank**: LinkSpy matches by name first and only
   creates a registry client if no name matches.
   - Success → the strip is replaced by four chips on refresh.
   - `Client.registryClientId` now holds the LinkSpy `clients.id` — the same
     UUID on both sides.
   - Sites under 60 days monitored show `Fragility settling`. That is Fresh Mode
     working, not a failure.
   - **If it creates rather than matches**, LinkSpy had no client of that name.
     Clear `registryClientId` on that row and delete the orphaned registry
     client before retrying.
5. **Then 2–4 more**, chosen by §6's criteria.
6. **Rollback:** unset `PRESENCE_CHIPS` on either surface. Written
   `registryClientId` values persist deliberately — they are registry
   annotations, not feature state.

## 8. Tripwires

| Tripwire | Status |
|---|---|
| T1 non-additive DDL | **not triggered** — no DDL; three new bulk *readers* over existing tables |
| T2 drift | **not triggered** — no migrations |
| T3 dump | n/a |
| T4 unattended writes | **not triggered** — read-only end to end, asserted by test in both repos |
| T5 exit test after one fix | see final report |
| T6 missing creds | **not triggered** — no new secrets; reuses `LINKSPY_API_URL` / `LINKSPY_API_KEY` |
