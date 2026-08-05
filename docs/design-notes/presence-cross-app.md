# Cross-app PRESENCE — Step 0 diagnosis + design note

**Date:** 2026-08-05 · **Branches:** `feat/presence-linkspy` (LinkSpy) ·
`feat/presence-dashboard` (Dashboard) · **Flag:** `PRESENCE=1`, default OFF,
flipped independently per surface.

Presence = quiet, in-view awareness of what the *other* app is currently
seeing about the thing you are already looking at. Read-only, derived, 60s
cached, staleness-over-errors, never blocking. No notifications, no push, no
new spine events, no stored presence state (Part C, honoured).

Architecture anchors: Seam 3 (§2, two read APIs), constitution rule 4 (state
via API, changes via events), rule 6 (staleness over errors), rule 8 (one
status vocabulary), §8.1 socket "a new public surface / read API — additive",
§8.2 "read APIs: additive changes ship in place, every response carries
`as_of`", §10 doctrine (closing certificate, not mid-build theatre — presence
is ambient context at the moment of sign-off, not a live build feed).

---

## 1. What the delivery bridge returns today

**Direction:** Dashboard → LinkSpy (Seam 3, second bullet). Producer lives in
the Dashboard, consumer in LinkSpy.

| Piece | Location |
|---|---|
| Producer | `dashboard: src/app/api/registry-bridge/delivery/route.ts` |
| Auth | inbound service bearer `DASHBOARD_BRIDGE_KEY`, `timingSafeEqual` |
| Key | `?registry_site_id=` → `Page.registrySiteId` (Seam 1 annotation) |
| Consumer | `linkspy: frontend/app/api/delivery/route.ts` (proxy, key server-side) |
| Consumer cache | 15 min in-memory + last-known-good → `stale: true` |
| Surface | `linkspy: frontend/components/DeliveryPanel.tsx`, first card of Site Detail → Overview |

Response shape (verbatim fields):

```jsonc
{
  "registry_site_id": "…", "as_of": "ISO",
  "deliverables": [{
    "name": "…", "qa_page_ref": "<Page.id>",
    "status": "IN_PROGRESS | IN_QA | LIVE",
    "checklist": { "passed": 0, "failed": 0, "na": 0, "total": 0 },
    "qa_score": 0,            // null while provisional
    "signed_off_at": "ISO",   // or null
    "deep_link_path": "/dashboard/clients/{c}/{p}/{page}"
  }]
}
```

The LinkSpy proxy signs `deep_link_path` into `open_in_qa_url` server-side via
`handoffUrl()` (`SPINE_SECRET` + `DASHBOARD_APP_URL`, TTL ≤ 300s).

**Gap for Part B:** the payload has `status` (so an `IN_QA` count is already
derivable — `DeliveryPanel` computes it today) but carries **no tester
identity at all**. One additive field is required: the assigned tester's
**first name only**.

**Verdict: extend in place.** Adding `tester_first_name` is an additive read-API
change (§8.2) — no `/v2/`, no new endpoint, existing consumers ignore it.

## 2. What LinkSpy exposes today for a "production presence" strip

**Direction:** LinkSpy → Dashboard (Seam 3, first bullet).

| Endpoint | Auth | Keyed on | Returns |
|---|---|---|---|
| `GET /api/qa-bridge/status` | qa-bridge **service key** | `qa_page_ref` (a deliverable) | delivery-check verdicts from latest stored results |
| `GET /api/qa-bridge/prefills` | qa-bridge **service key** | `deliverable_id` | machine pre-fills per check_key |
| `GET /api/registry/clients`, `…/sites`, `…/deliverables` | qa-bridge service key | — | registry identity |
| `GET /api/sites/{site_id}/sentinel` | **session** `require_site_access("client_viewer")` | `site_id` | the exact payload presence needs |

The data a production-presence strip needs already exists and is already
shaped — it is simply behind the wrong door:

- `backend/sentinel.py :: summarize_sentinel(status, pings)` — pure, returns
  `cards[]` (`key` ∈ ssl · domain · index · uptime; `label`, `escalation` ∈
  critical/warn/notice/unknown/ok, `fact`, `days`), plus `worst`, `all_clear`,
  `last_checked`, `uptime_pct`, `down`. Cards are already sorted
  most-urgent-first ("proximity = prominence").
- `backend/database.py :: list_incidents(site_id)` — `sentinel_incidents`
  rows (`id`, `down_at`, `restored_at`); **open = `restored_at` is null**,
  opened after 2 consecutive failed uptime pings (`sentinel.py:325`).
- `backend/main.py :: _sentinel_payload(site_id)` composes both.

**Gap for Part A:** every existing service-key endpoint is keyed on a
*deliverable* (`qa_page_ref` / `deliverable_id`), never on a **site**; and the
only site-keyed sentinel endpoint requires a **browser session**, which a
server-to-server bridge call does not have. There is no way to satisfy Part A
with existing endpoints.

**Verdict: one new endpoint is genuinely required** —
`GET /api/qa-bridge/presence?registry_site_id=…`, service-key auth, reusing
`_qa_authenticate` + `_qa_rl` and the pure `summarize_sentinel`. This lands in
an existing socket (§8.1 "a new public surface … reads via tokened views";
§8.2 additive read API), so **no ADR is required** — it adds nothing to the
architecture, only to the surface area of an existing seam.

`registry_site_id` **is** LinkSpy `sites.id` — confirmed end-to-end:
`Page.registrySiteId` ← registry linking UI → passed as `site_id` to
`/api/delivery` → forwarded as `registry_site_id` to the Dashboard bridge.
No translation layer needed.

---

## 3. Challenges to the proposed shape (raised before code)

**C1 — Dashboard side: two LinkSpy-sourced strips would stack.** The checklist
view already renders `StillTrueHeader` immediately above the checklist, also
sourced from LinkSpy. *Resolved, not blocking:* the content is disjoint —
StillTrue reports **per-delivery-check verdicts** ("is this check still
true"), presence reports **production infrastructure** (SSL, domain, uptime,
indexability, open incidents), which StillTrue never shows. Presence sits
above the `QA checklist` heading; StillTrue stays where it is. Distinct
purple tint keeps the registers separate. Accepted as specified.

**C2 — LinkSpy side: the presence line duplicates a number the Delivery panel
already prints.** `DeliveryPanel` is the *first card* of the Overview and its
summary line already reads "N deliverables · M signed off · K in QA". A
header line saying "2 deliverables in QA" therefore restates a figure visible
~200px below it. This is a genuine cost (constitution rule 8 — one status
vocabulary; two renderers of one number drift). *Recommended shape:* fold the
tester names into the existing `DeliveryPanel` summary clause instead of a
second strip.
*Decision taken:* implement as specified (header line), because glance-level
awareness above the fold is the whole point of presence and the Delivery card
is a *detail* surface — but mitigate the real risk: **both read the same
upstream field from the same producer**, so there is exactly one source of
truth for "in QA". Flagged for the operator; trivially reversible by unsetting
the flag. Recorded here rather than silently absorbed.

**C3 — cache split.** `/api/delivery` caches 15 min; presence is specified at
60s. Rather than give one route two freshness policies, presence gets a
sibling route `/api/presence/delivery` with its own 60s cache calling the same
Dashboard producer (the prompt permits "or a sibling endpoint"). `DeliveryPanel`
and `/api/delivery` are then **untouched in both flag states**.

**C4 — deployment target is misstated in the brief.** The brief says gate the
LinkSpy strip behind `PRESENCE=1` "on Railway". Railway hosts the **FastAPI
backend**; the LinkSpy **frontend is a separate Vercel project**
(`brokenlinkchecker`) — per `INFRASTRUCTURE.md` topology. The presence line is
rendered by the Next.js frontend, so `PRESENCE=1` belongs on **Vercel
`brokenlinkchecker`**, not Railway. The new backend read endpoint needs no
flag: it is an authenticated read API, and rendering is what the flag gates.

**C5 — `INFRASTRUCTURE.md` is stale.** Discrepancy **D1** declares
`DASHBOARD_BRIDGE_URL`/`DASHBOARD_BRIDGE_KEY` "orphaned — target route does
not exist". That route now exists (Dashboard commit `db85693`). D1 is resolved
by reality; the doc is updated alongside this work in both mirrored copies.

---

## 4. Design (as built)

### Part A — Dashboard "Production presence" strip

```
LinkSpy backend (Railway)                Dashboard (Vercel)
GET /api/qa-bridge/presence      ──▶  src/lib/linkspy/presence.ts (60s cache,
    ?registry_site_id=…                 last-known-good, never throws)
    Bearer LINKSPY_API_KEY            ──▶ <ProductionPresence/> above the
                                          QA checklist heading, PRESENCE=1 only
```

Signals rendered, most-urgent-first, one line each; zero signals → **strip not
rendered at all** (no "all good" state — quiet by design):

| Source | Renders as |
|---|---|
| open incident (`restored_at == null`) | `1 open incident · disaster sentinel` |
| sentinel card, escalation ∈ critical/warn | `⚠ SSL expires in 3 days · monitoring holding` |
| unreachable + no cache | `Production status unavailable` (muted, one line) |
| unreachable + cache | last-known-good + `as of …` |

Each signal links to LinkSpy through a **server-signed handoff token**
(`signHandoff` / `handoffUrl`, TTL ≤300s) targeting
`/dashboard/{site_id}` — tokens are minted in the server component and never
in the browser.

Pure shaping lives in `src/lib/linkspy/presence-shape.ts` (no I/O) so
flag-off/one-signal/three-signal/stale/unreachable are all unit-testable
without a network.

### Part B — LinkSpy "Delivery presence" line

```
Dashboard (Vercel)                      LinkSpy frontend (Vercel)
GET /api/registry-bridge/delivery ──▶  /api/presence/delivery (60s cache,
    + tester_first_name (additive)       last-known-good) ──▶ header line on
    Bearer DASHBOARD_BRIDGE_KEY          Site Detail Overview, PRESENCE=1 only
```

Renders `🧪 2 deliverables in QA · Anaum, Babar` with a signed handoff into
the Dashboard client view. Zero in-QA deliverables → **line hidden**.
Unreachable → hidden (quiet), never an error box.

**PII:** first names only. The producer splits on whitespace server-side and
emits only the first token; emails, ids and surnames never cross the bridge.

### Flag semantics

`PRESENCE` is read **server-side only**, at render time. Unset/any value other
than `1` ⇒ the fetch never happens and the component returns `null` ⇒ the DOM
is byte-identical to today. Rollback = unset the var and redeploy.

---

## 5. Tripwires

| Tripwire | Status |
|---|---|
| T1 non-additive DDL | **not triggered** — no DDL of any kind |
| T2 drift | **not triggered** — no migrations |
| T3 dump | n/a — no migration |
| T4 unattended writes to QA rows | **not triggered** — every path is `SELECT`-only; the Dashboard producer has no write, the LinkSpy endpoint calls read helpers only |
| T5 exit test fails after one fix | see final report |
| T6 missing creds | **not triggered** — zero new secrets; both directions reuse credentials already provisioned |
