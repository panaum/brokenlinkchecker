# Apexure Platform — Architecture Roadmap v7
### Unifying LinkSpy and the Deliverables Dashboard into one quality system

**Status:** proposal for review — Anaum / Waseem / Malik
**Principle:** federation, not fusion — two engines, one identity, one event
spine, one shell. **North star: the Quality Flywheel** — the two apps hold
two halves of one intelligence, and joining them creates a learning loop no
agency has. **v3 addition: this architecture is designed to absorb futures we
haven't chosen yet** — §8 names its extension points, its versioning rules,
and the evolution scenarios it is pre-shaped for.

---

## 0. What the two apps actually are (corrected after full review)

| | LinkSpy | Deliverables Dashboard |
|---|---|---|
| Phase of life | PRODUCTION — continuous verification, incidents, monitoring, client portal | DELIVERY — build ops, human QA, sign-off, team workload |
| Knows | what breaks in the wild, when, why, how long fixes hold, per-site fragility, cross-site third-party patterns | issues found at delivery, per platform (CF 13.8/page vs LearnWorlds 2.5), per developer (defect leaderboards), delays, repetitive bugs, monthly delivery reports |
| Already has | incident spine, ledgers, fragility score, cross-site indices | Insights engine, needs-attention feed ("Live without QA sign-off"), Run AI QA, team analytics |
| Blind to | how the thing was built, by whom, what QA found | everything that happens after sign-off |

**The v2 realization:** each app has independently evolved an intelligence
layer over ITS half of the lifecycle. The Deliverables Insights page
("ClickFunnels is your most defect-prone platform") is the exact mirror of
LinkSpy's fragility/cost indices ("this chat widget adds 290ms across 6
sites"). The innovation is not connecting the apps — it is JOINING THE TWO
DATASETS. Delivery quality × production quality = the complete truth about
what it costs to build on each platform, which builds hold up, and which
checks actually prevent real-world failures.

---

## 1. The Quality Flywheel (the north star)

```
        BUILD ──────► QA SIGN-OFF ──────► PRODUCTION
          ▲     (machine pre-fill,          (continuous
          │      human confirms)             monitoring)
          │                                      │
          │                                      ▼
   CHECKLIST EVOLVES ◄──── GAP ANALYSIS ◄── INCIDENT
   (new template item)   ("which delivery
                          check would have
                          caught this?")
```

Every production incident closes with one new question, answered on the
incident record: **"Would any delivery check have caught this?"**

- YES, and it passed at delivery → the world changed after launch (drift) —
  monitoring's job, working as intended.
- YES, but it was marked N/A or missed → a QA process finding, routed to the
  Deliverables app.
- **NO check exists → a checklist-template candidate is born.** A human
  reviews and promotes it; every future deliverable inherits the check.

This is the flywheel: production failures permanently upgrade the delivery
process. The checklist stops being a static document and becomes an evolving
asset trained on real-world evidence. After a year, Apexure's QA checklist is
literally the distilled failure history of hundreds of live sites — an asset
no competitor can copy, because it cannot be written, only earned.

Three joined-intelligence products fall out of the same join:

1. **Platform Lifetime Cost Index** — Deliverables knows issues-per-page at
   delivery per platform; LinkSpy knows incidents/fragility per platform in
   production. Joined: "ClickFunnels: 13.8 issues at delivery AND 2.3× the
   production incident rate — the true cost of building on it." Directly
   prices your platform recommendations to clients.
2. **Recurring-issue unification** — the Deliverables "repetitive bugs"
   counter (25) and LinkSpy's recurring-fingerprint detection are the same
   concept on either side of launch. One shared taxonomy: an issue that
   recurs at delivery AND resurfaces in production is a template/process
   defect, flagged once, fixed at the root.
3. **Build-cohort durability** (handle with care) — production incidents can
   join back to the build's metadata (platform, template, month — NOT
   individual leaderboards by default). Constructive use: "pages built on
   template X in Q1 are failing at 3× rate — one root fix." The
   developer-level join stays internal-analytics-only, framed as
   process-improvement, never surfaced as blame. This rule is written down
   because the data will tempt otherwise.

And one immediate, cheap win from the join: the Deliverables "needs
attention" feed flags **"Live without QA sign-off"** — but the Deliverables
app only knows "live" if someone sets the status. LinkSpy KNOWS what is
actually live (it monitors it). Post-join, that flag becomes automatic and
complete: any URL LinkSpy observes serving traffic whose deliverable lacks
sign-off is flagged without human bookkeeping.

---

## 2. Where the apps join — four seams (unchanged mechanics, sharper content)

### Seam 1 — IDENTITY: the Registry
LinkSpy's tenancy (workspaces → clients → sites, roles, RLS) is promoted to
the system of record. It gains `deliverables` (kind: page | project | site —
per the granularity question, answer: either, with a kind field). The
Deliverables app annotates its entities with `registry_client_id` /
`registry_deliverable_id`; it never renames its own. The qa_bridge_map built
this week is the embryo.

**Hygiene pass, now scoped by real data:** 89 "clients", 99 projects, 231
pages. Most client entries are deliverable-shaped ("Build | Funnel 2 LP").
The mapping UI (Phase 1) presents each for one decision: real client → link
to registry client; deliverable-shaped → assign to its true client (create
if needed). ~2–3 focused sessions, no deadline pressure, tracked in the UI.

### Seam 2 — EVENTS: outbox/inbox with signed webhooks
Unchanged mechanics (outbox row in the same transaction as the change; HMAC
delivery loop with retry + dead-letter; inbox with idempotency keys). Event
catalog v2 — the flywheel adds three:

| Event | Emitter | Consumers |
|---|---|---|
| deliverable.created | Deliverables | LinkSpy (registers it — does NOT trigger the battery) |
| deliverable.ready_for_qa | Deliverables | LinkSpy (THIS fires the battery — human-confirmed ready) |
| qa.completed | Deliverables | LinkSpy (timeline, auto-enroll monitoring) |
| scan.completed | LinkSpy | Deliverables (refresh "still true today") |
| incident.opened / resolved | LinkSpy | Deliverables (flag deliverable) |
| **incident.gap_analysis** | LinkSpy | Deliverables (checklist-candidate queue) |
| **checklist.item_promoted** | Deliverables | LinkSpy (map new item into check catalog if machine-verifiable) |
| **deliverable.live_observed** | LinkSpy | Deliverables (auto "live without sign-off" flag) |

Every event lands in `client_timeline` (LinkSpy, keyed by registry IDs) —
the deal-to-renewal river that the cockpit, boardroom link, and certificates
read.

### Seam 3 — STATE: two read APIs
- LinkSpy → Deliverables: the existing qa-bridge status endpoint ("still
  true today"). Live as of this week.
- Deliverables → LinkSpy (new): `GET /registry-bridge/delivery` —
  deliverables, checklist %, QA score, sign-off state, developer/tester,
  deep link. Feeds the cockpit Delivery panel AND the joined-intelligence
  queries (platform index needs delivery-issue counts).

### Seam 4 — SURFACE: one shell, one workbench, one intelligence view
- LinkSpy = the shell: cockpit gains the Delivery panel; the client
  portal/boardroom story is unchanged.
- Deliverables = the team's workbench: checklist work, sign-off, team ops
  stay exactly where Atul and the testers live today.
- **NEW — the joined Insights view:** the Deliverables Insights page and
  LinkSpy's indices merge into ONE intelligence surface (lives in the shell,
  reads both datasets via Seam 3): platform lifetime cost, quality trend
  across delivery AND production, recurring-issue unification, flywheel
  status ("4 checklist items born from production incidents this quarter").
  This page is the executive proof that the two tools became one brain.
- Visual seam-hiding: shared design tokens (purple, type, status colors) in
  both apps; deep links both ways carrying registry IDs.
- Public-surface decision (Phase 4 review): ONE client-facing link policy —
  the QA certificate and the boardroom link converge or divide by audience
  explicitly.

---

## 3. The engine room — one jobs table (unchanged, still first)

All background work — monitoring, tracer, sentinel, reports, event delivery,
auto-fill batteries, gap-analysis jobs — through ONE Postgres-backed `jobs`
table in LinkSpy (status, idempotency_key, attempts, run_after, per-domain
caps). APScheduler ticks and inbound events both just enqueue; one worker
drains. Deliverables' outbox drains via a Vercel cron hitting a route — its
volume is tiny. Exit test: kill the Railway process mid-scan; nothing lost,
nothing doubled.

**Note discovered in review: the Deliverables app already has "Run AI QA".**
Phase 3's auto-fill must ABSORB or coherently coexist with it — one
pre-fill concept, not two competing ones. Diagnose what Run AI QA does today
before building (open question #6).

---

## 4. The flagship flow — QA auto-fill (upgraded by the flywheel)

**Design correction (accepted): creation and readiness are TWO moments.** A
deliverable is created (assigned, named, URL optionally a staging link) long
before it is finished. Firing the battery on mere creation scans half-built
pages and produces garbage pre-fills — worse than none, because they teach
the tester to distrust the automation on day one. So the battery keys off a
HUMAN-CONFIRMED READY SIGNAL, not existence.

0. Page created in Deliverables (client, name, platform, developer, tester,
   URL) → `deliverable.created` — REGISTERS it on the registry, nothing else.
1. Developer/lead marks it Ready for QA (status transition, or an explicit
   "Run checks" button — disabled-with-reason if URL is blank) →
   `deliverable.ready_for_qa`. THIS is the trigger.
2. LinkSpy runs the full battery (links, forms, tracking, SSL, load time —
   the existing catalog) against the URL.
3. Machine-checkable items render PRE-FILLED: "machine-verified: PASS —
   evidence →". **The human still confirms — sign-off remains a human
   signature with machine evidence attached.** (~60% of manual QA labor
   deleted; 100% of accountability retained.)
4. Sign-off → `qa.completed` → monitoring auto-enrolls (default weekly,
   agency notified, one-click off) → "still true today" takes over forever.
5. **The flywheel turn:** any later production incident on this deliverable
   runs gap analysis (§1) — and the checklist that QA'd it can grow because
   of what production taught.

---

## 5. Roadmap — phases, each independently shippable

- **Phase 0 — Foundations:** jobs table + worker; ENTITY-MODEL.md argued on
  paper; Run-AI-QA diagnosis.
- **Phase 1 — Registry:** deliverables concept, Registry API, mapping UI,
  the 89-entity hygiene pass (tracked, unhurried).
- **Phase 2 — Event spine:** outbox/inbox, HMAC loops, v2 catalog,
  client_timeline, connection-health panels in BOTH apps ("bridge: connected
  · last event 2m ago · key valid ✓") — the antidote to key-rotation
  afternoons.
- **Phase 3 — Auto-fill (flagship):** the §4 flow end to end, absorbing Run
  AI QA. Exit: a new deliverable goes URL → pre-filled → human-confirmed →
  monitored with zero manual copying.
- **Phase 4 — The shell + the joined Insights view:** cockpit Delivery
  panel; the merged intelligence page (platform lifetime cost, unified
  recurring issues, flywheel counter); shared tokens; the public-surface
  decision with real usage data.
- **Phase 5 — The flywheel closes:** gap-analysis on incident resolution,
  checklist-candidate queue in Deliverables, human promotion flow,
  `checklist.item_promoted` back into LinkSpy's catalog. Exit: one real
  production incident births one reviewed checklist item that a later
  deliverable is checked against.
- **Phase 6 — CRM (Replit, in-house, both ends controlled):** adapter file;
  deal.won → registry client + deliverable shell + checklist template;
  milestones (qa.completed, monitoring.active, first report) written back.
- **Phase 7 — Lived-experience decisions (deferred on purpose):** auth
  unification; absorbing the Deliverables UI into the shell; developer-level
  production analytics (only with team buy-in, only as process improvement).

---

## 6. The constitution (rules that keep it solid)

1. No shared database connections. Ever. IDs and events, not schemas.
2. Events written in the same transaction as the change, or they don't
   count.
3. At-least-once delivery + idempotent consumption everywhere.
4. State via API, changes via events.
5. Machine pre-fills; humans sign. No delivery verdict without a human
   confirmation on record.
6. Staleness over errors — either app unreachable, the other renders
   last-known-good with its timestamp.
7. Keys are boring: per-direction service keys, health-panel visible,
   test-before-save, never rotated casually.
8. One status vocabulary and one color system across both apps.
9. Every phase independently shippable; any phase can pause a month without
   rot.
10. **Flywheel data is for process, not blame.** Build-cohort and
    developer-level joins stay internal, constructive, and opt-in for the
    team. Written down now, before the data makes it tempting.

---

## 7. Open questions (argue on this document — answers become ADRs 001–007)

1. Deliverable granularity — proposal: kind field (page | project | site).
2. QA certificate's data source post-spine — own DB now, timeline-fed at
   Phase 4?
3. Monitoring auto-enroll on qa.completed — proposal: ON at weekly, notify,
   one-click off.
4. Hygiene-pass ownership and pace — who runs the 2–3 mapping sessions?
5. Replit CRM: webhooks today, or Phase 6 adds its outbox?
6. **What does "Run AI QA" currently do, and does auto-fill replace it or
   feed it?**
7. Gap-analysis authorship: template candidates drafted deterministically
   from incident class — is a human-written rationale required at promotion?
   (Proposal: yes, one sentence, recorded.)

---

## 8. Designed for change — how this architecture absorbs the future

An architecture is "smart" not when it predicts the future but when the
futures it didn't predict are cheap. This section makes that a discipline,
not a hope: named extension points, versioning rules, a decision record, and
the evolution scenarios pre-mapped so the day one arrives, the answer is a
lookup, not a redesign.

### 8.1 Extension points (the places new things plug in)

Every anticipated kind of growth has ONE designated socket. Adding to a
socket never requires touching the others.

| You want to add… | The socket | What it costs |
|---|---|---|
| A new automated check (e.g. accessibility, Core Web Vitals) | the check catalog (versioned, provenance per row) + one jobs `kind` | a catalog row, a runner function, a checklist mapping — no schema change |
| A new event between apps | the event catalog + one inbox handler | additive only; consumers that don't care ignore it |
| A new app joining the platform (a third tool, the CRM, a future client-mobile app) | its own outbox/inbox pair + registry ID columns | it becomes a station on the spine; zero changes to existing apps |
| A new CRM / a replaced CRM | the adapter file | swap one file; the spine never knows |
| A new deliverable kind (email template? full app?) | `deliverables.kind` + a checklist template | enum value + template, nothing structural |
| A new public surface (certificate variant, embed, API consumer) | reads `client_timeline` + ledgers via tokened views | ledgers are append-only sources of truth; surfaces are disposable renderers |
| A new CMP / builder / platform profile | the respective profile tables (already versioned with provenance) | one profile row |
| Replacing the jobs table with a real queue at scale | the enqueue/drain interface | business logic never imported the table directly — rule, not accident |

**The socket rule:** if a proposed change doesn't fit an existing socket,
that's not a blocker — it's a signal to STOP and write an ADR (§8.3),
because you're changing the architecture, not extending it.

### 8.2 Versioning rules (what may change, what may only grow)

- **Events:** every event carries `schema_version`. Fields are ADDED, never
  renamed or removed; a breaking need = a NEW event name (`qa.completed.v2`
  is forbidden — `qa.signoff_recorded` is how you'd actually evolve it).
  Consumers tolerate unknown fields by construction.
- **Ledgers (tracer runs, consent sessions, bundles, timeline):**
  append-only forever, format_version stamped per row, judged-by versions
  recorded (engine + ruleset that produced each verdict) so every historical
  row remains interpretable and reproducible after the rules evolve.
  **Ledgers cannot be backfilled — which means: when in doubt, start
  recording NOW, render later.** Storage is cheap; history is not
  purchasable.
- **Read APIs:** versioned path prefix only when breaking (`/v2/`); additive
  changes ship in place. Every response carries `as_of`.
- **Catalogs and profiles (checks, builders, CMPs, promise rules):**
  versioned tables with provenance — every row states why it exists and what
  it caught. A catalog you can't audit is a catalog you'll fear to change.
- **The registry:** IDs are eternal. Entities merge (two clients discovered
  to be one) via a `merged_into` pointer — never by deleting an ID that
  events and ledgers reference.

### 8.3 Decision records (how future changes get made, not just built)

A lightweight ADR log lives at `docs/decisions/NNN-title.md` — one page:
context, options, decision, consequences, date, who. Rules:

- Anything that adds a socket, breaks a versioning rule, or touches the
  constitution REQUIRES an ADR before code.
- ADRs are immutable once accepted; reversals are new ADRs that supersede.
- This roadmap itself is ADR-000. The open questions in §7, once answered,
  become ADRs 001–007.

This is the mechanism that keeps the architecture smart after the people who
argued it have moved on to other fires: the reasoning survives, so future
changes argue with the reasoning instead of rediscovering it.

### 8.4 Evolution scenarios (pre-mapped, so arrival day is a lookup)

**S1 — Scale 10× (sites, scans, events).** The jobs table's drain loop gets
competition for the single worker → add workers with row-locking (already
`locked_by`-shaped), then swap the drain for a real queue behind the same
interface. Ledger tables partition by month. Nothing above the jobs
interface changes. *Pre-commitment made today: business logic enqueues via
one function, never inserts into `jobs` directly.*

**S2 — LinkSpy becomes a product for other agencies (the layer-5 horizon).**
The registry already speaks workspaces; multi-agency = multiple workspaces
with billing/entitlements attached. The entitlement layer (from the earlier
monetization plan) gates features per workspace. The Deliverables app
becomes an OPTIONAL station other agencies may not have — which is exactly
why the spine treats it as a peer, not a dependency. *Pre-commitment: no
LinkSpy feature may hard-require the Deliverables app; joined-intelligence
views degrade to LinkSpy-only data gracefully.*

**S3 — AI agents become fixers.** The reproduction bundle + verify loop is
already the audit substrate for machine-executed fixes; self-heal's rails
(allowlist, PR-not-push, human merge) are the containment. When agents
arrive, they consume bundles and produce PRs through the SAME rails humans
review today. *Pre-commitment: no fix path exists that bypasses the
evidence-in / verification-out contract.*

**S4 — A real-time need appears (live dashboards, instant alerts).** The
outbox pattern's latency is seconds-to-minutes; if a surface someday needs
sub-second, add a push channel (SSE/websocket) fed BY the same inbox
handlers — the spine remains the source, the channel is a renderer. *Never
let a real-time feature write around the spine.*

**S5 — Auth unification day.** Both apps on NextAuth already; unification =
a shared OIDC issuer (or one app becoming the issuer) with registry-mapped
identities. Deferred deliberately (Phase 7), and cheap BECAUSE identities
are already registry-keyed. *Pre-commitment: no per-app user tables grow
fields the registry should own.*

**S6 — An app is retired or rewritten.** Because stations share only IDs
and events, a rewrite replays its inbox to rebuild state, keeps its
registry annotations, and swaps in behind the same seams. The federation's
quiet superpower: any single codebase is replaceable without a platform
migration.

### 8.5 The change budget (what's cheap, what's ruinous — decided now)

CHEAP forever, by construction: new checks, new events, new surfaces, new
profiles, new apps on the spine, swapping the CRM, swapping the queue,
rewriting either UI.

EXPENSIVE forever, so get right in Phase 0–2 and then defend: registry ID
semantics; ledger schemas (append-only means mistakes are permanent
residents — review ledger migrations at double strictness); the event
catalog's NAMES (renames ripple everywhere); the constitution.

The review heuristic that follows: **spend review minutes proportional to
permanence.** A UI PR gets a skim; a ledger or registry migration gets the
full adversarial read.

---

## 9. Failure modes & guardrails (the architecture critiquing itself)

Federation's honest cost: one hard problem (merging codebases) traded for a
distributed-systems problem (keeping two databases in agreement) — and
distributed systems fail QUIETLY. The failure modes, ranked, each with its
guardrail. The guardrails are not polish; they are the price of the choice.

| # | Failure mode | How it looks | Guardrail |
|---|---|---|---|
| 1 | **Split-brain drift** — the two DBs disagree and nothing errors | QA says "signed off", LinkSpy says "never QA'd"; both dashboards confident | **Reconciliation routine** (nightly): walk mapped pairs, compare state. Classify: missed event → AUTO-REPLAY (self-heal, log only); genuine contradiction → alert with both records side-by-side. ~90% of drift self-corrects. |
| 2 | Eventual consistency confusing humans | Atul signs off, cockpit doesn't show monitoring yet → "it's broken" | Optimistic UI with reconciled truth (§10) — the human never feels spine latency. |
| 3 | Cross-system debugging archaeology | "Why didn't monitoring enroll?" has five suspects | **Event trace view**: one lookup shows written → delivered (attempt n) → processed/dead-lettered, next to the connection-health panel. |
| 4 | The Vercel-cron weak link | QA-side outbox drain silently stops; events just sit | **Heartbeat routine**: QA outbox emits `heartbeat` hourly even when idle; LinkSpy alerts on >2h silence. Monitor the messenger with its own channel. |
| 5 | Contract rot | A renamed API field quietly breaks the cockpit a week later | **Contract tests in CI**: one shared spec (event schemas + API shapes); both repos' builds fail BEFORE deploy on any mismatch. §8.2 mechanized. |
| — | Gap detection latency | A lost event isn't noticed until nightly reconciliation | **Sequence numbers per entity stream**: inbox sees #7 without #6 → requests replay immediately. One integer column; near-real-time consistency. |

## 10. The smoothness layer (QA automation as a felt experience)

The same investment — state that is traceable, replayable, and
self-announcing — is simultaneously the reliability fix and the UX fix.

**Workflow reality (locked with the team):** the QA checklist is a CLOSING
CERTIFICATE, filled at the END of the build — after the manual compare pass
and the log-to-Trello / dev-fix loop are already done. It is NOT the working
surface the tester stares at during QA. So LinkSpy's job is narrow and clear:
have the machine-verifiable checklist items ALREADY ANSWERED, freshly, by the
time the tester reaches sign-off. No mid-build theatre — just a closing
checklist that fills itself for the mechanical rows.

1. **Optimistic UI, reconciled truth.** Sign-off immediately renders
   "monitoring: enrolling ✓" locally; the event flows; confirmation quietly
   solidifies it (or snaps back with a reason — rare, honest). Same pattern
   as the re-check button, applied at the seam.
2. **Pre-answered at sign-off, kept fresh.** The battery runs on
   `deliverable.ready_for_qa` and its results are held; when the tester opens
   the closing checklist, machine-verifiable rows are already filled with
   evidence. If the held results are older than a freshness window (e.g. 1h)
   at open time, offer a one-click "refresh checks" — freshness over
   eagerness. (No live-streaming animation: nobody watches the checklist
   mid-build in this workflow.)
3. **One-gesture confirmation with graduated trust.** V1: "Confirm all
   machine-passed (N)" in one click; fails reviewed individually. V2 (earned):
   per-check-type reliability stats from flywheel data ("SSL: 200 runs, 0
   human overrides") let check types GRADUATE to auto-confirm — human review
   narrows to where machines are measurably unreliable. Autonomy is earned
   check-type by check-type, on the record.
4. **Failed machine checks route to the fix loop, not the checklist.** A
   machine-found failure carries its evidence + fix suggestion, but it belongs
   to the developer's fix loop (today: Trello — see §11.1), not the tester's
   closing checklist. The checklist records the final verified state; the
   fixing happens upstream of it.

## 11. Routines (the standing heartbeat of the platform)

All recurring work is a ROUTINE: a named, scheduled job on the jobs table
(LinkSpy) or the drain cron (Deliverables), with an owner, a cadence, and a
defined alert condition. Routines are configuration, not code sprawl — one
catalog, visible in an admin "Routines" panel showing last run / next run /
last outcome per routine. A routine that hasn't run on schedule is ITSELF an
alert (the panel is self-monitoring).

| Routine | Cadence | Does | Alerts when |
|---|---|---|---|
| monitoring scans | per sites.freq (default daily) | existing scan pipeline | provable new breaks (existing rules) |
| tracer runs | daily 06:00 site-tz | lead-delivery verification | partial/failed arrival, failed cleanup |
| sentinel probes | daily + 5-min uptime ping | SSL/domain/visibility/uptime | ladder thresholds, 2-strike downtime |
| ads waste-guard | daily | re-verify ad destinations | live ad → provably dead page |
| consent observations | weekly per enrolled page | cold/reject/GPC renders | new observation (drift) |
| vigilance reports | monthly per site | compose + archive report | generation failure |
| **outbox drains** | continuous (LinkSpy worker) / 5-min cron (QA) | deliver spine events | dead-letter count > 0 |
| **heartbeat** | hourly (QA outbox) | liveness signal | >2h silence (LinkSpy side) |
| **reconciliation** | nightly | walk mapped pairs, auto-replay missed events | genuine contradiction found |
| **derived recomputes** | nightly | perf ledger, fragility, indices | recompute failure |
| **ledger integrity** | weekly | re-hash bundles/ledgers vs manifests | any hash mismatch (critical) |
| speculative batteries | on deliverable.ready_for_qa | pre-fill battery | battery crash (job-level) |

Rule: no scheduled behavior exists outside this catalog. A new recurring need
= a new routine row, an ADR only if it needs a new socket.

### 11.1 Trello — the deferred third view (and the real ready signal)

Two apps are in scope now (LinkSpy + Deliverables). Trello is the THIRD view,
deferred — but noted here because it is not merely a future feature, it is:

- **The real-world source of `deliverable.ready_for_qa`.** Today a developer
  moving a Trello card to the QA column IS the ready signal. When Trello is
  integrated, that card-move fires the event directly; until then, the signal
  is whatever manual status the team sets in the Deliverables app.
- **The developer-facing surface.** The flywheel's checklist-candidates and
  machine-found failures both need to reach DEVELOPERS, not just testers —
  and that is exactly what a Trello view provides. Build it ONCE for both
  needs (issue routing + ready-signal), when its phase comes.

Deferred, not forgotten: the architecture already speaks in events, so Trello
joins later as another station on the spine with zero rework.

---

## 12. The solidified v1 cut (adversarial pass, accepted)

The v4 design is the north star; THIS is what actually gets built first.
Rule zero: this architecture must never freeze the revenue track — the
tracer pilot and the first paying client outrank every phase below P3. Cap
platform work at a share of capacity.

| Phase | KEEP (v1) | TRIMMED TO | DEFERRED (add on evidence) |
|---|---|---|---|
| P0 | jobs table + worker; ENTITY-MODEL.md (1 page); **Run-AI-QA diagnosis as a GATE — answered before anything else** | — | routines admin panel (logs suffice) |
| P1 | registry + deliverables; **mapping-at-creation** (one field on the QA create form) | hygiene pass → on-demand only: historical entities map when something needs them | wholesale 89-entity mapping session |
| P2 | outbox/inbox; HMAC; connection-health panel; nightly reconciliation w/ auto-replay; heartbeat | **2 events only: deliverable.ready_for_qa, qa.completed** (creation event added when it has a consumer) (others when consumers exist); shared schema file both repos import (instead of CI contract-test rig) | seq-replay protocol (seq COLUMN kept, protocol later); event-trace UI |
| P3 | everything — speculative battery, pre-fill streaming, human-confirm, fix-attached failures, auto-enroll. **This is the payoff.** | — | graduated trust (needs months of confirm data) |
| P4 | cockpit delivery panel; **signed handoff links pulled forward** (short-lived token, same pattern as cert URLs — cross-app deep links must not hit a login wall) | joined insights → LinkSpy-side data first; the platform-cost join needs months of P2 data anyway | — |
| P5–P6 | on the roadmap, unscheduled | — | scheduled only after P3 has lived a month in the team's hands |

Rationale kept on record: everything expensive-to-reverse survives the cut
(ledger schemas, registry semantics, outbox-in-transaction, machine-prefills
/human-signs); everything trimmed is cheap to add when evidence demands it —
which is §8.5's change-budget philosophy applied to the roadmap itself.

Known risks carried consciously: (1) hygiene-as-you-go means historical
analytics stay partial until entities are touched — accepted; (2) two-event
spine means the flywheel and live-observed flag wait — accepted; (3) the
primary QA tester is also the builder (111 pages QA'd), so P3 adoption risk
is unusually low — noted as a tailwind, not a plan.
