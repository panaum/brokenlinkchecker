# Design Note — Phase 5: The Quality Flywheel

**Status:** proposed (autonomous — code proceeds after commit).
**Branches:** `feat/flywheel-gap` (LinkSpy) · `feat/flywheel-queue` (Dashboard).
**Architecture:** v7 §1 (the flywheel: production incident → "would a delivery
check have caught this?" → new checklist candidate → human promotes → every
future deliverable inherits it) + §8.2 (versioned catalogs with provenance).
**Constitution:** additive-only; deterministic rule-based classifier (NO LLM);
new behaviour behind `FLYWHEEL` DEFAULT OFF; **rule 10 — nothing keyed to
individual developers**; candidates live in their OWN table; templates are
written only by the human PROMOTE action (T4).

---

# PART 1 — Diagnosis (STEP 0, read-only)

## Dashboard — the checklist template model
- **`ChecklistTemplate`** (`id`, `name` unique, `platform?`, `isDefault`) →
  **`ChecklistTemplateItem`** (`id`, `templateId`, `category`, `name`,
  `hasDualValue`, `isMeasurement`, `order`). Seed source: `src/lib/qa-template.ts`.
- On page creation, `createPageWithCert` seeds **`QACheckItem`** rows
  (`category`, `name`, `result` PASSED|FAILED|NA) from the best-matching template
  (platform → default → built-in `QA_TEMPLATE`).
- **Item vocabulary / key:** items are identified by **`(category, name)`** —
  there is **no stable slug/key column** (confirmed in Phase 1). So "promote" =
  insert a `ChecklistTemplateItem` (category + name). New deliverables inherit
  it; **existing pages are untouched** (they already seeded their items).

## LinkSpy — the incident classification surface
Everything a resolved incident carries that a deterministic classifier can key on:
- **Findings** (`findings`): `bucket` ∈ {`broken`, `dead_cta`, `unverifiable`},
  `zone`, `priority`, `reason`, `status` ∈ {open, resolved, verified_fixed},
  `resolved_at`. Resolution paths: diff-driven (`_save_snapshot_sync` stamps
  `resolved_at` when a finding disappears) and `verify_finding` →
  `mark_finding_verified` (→ `verified_fixed`).
- **Sentinel:** `sentinel_incidents` (`down_at`/`restored_at`) = **uptime**;
  plus SSL / domain countdowns and **indexability** (`robots` / `noindex` /
  `sitemap` via `indexability_verdict`).
- **Watchdog:** third-party host outages (`integration_audit.classify_host`
  categories: Analytics / Tag Management / Advertising / …).
- **Ads-guard:** live ad destination → dead page.
- **Perf:** load-time regression (perf ledger).

## Battery check keys (the coverage vocabulary — `qa_catalog.CATALOG`, v1)
`ssl_valid`, `ssl_expiry`, `domain_expiry`, `uptime`, `broken_links`,
`ga4_installed`, `gtm_setup`, `pixel_present`, `page_load_time`, `forms_submit`.

## LinkSpy outbox — DOES NOT EXIST
Phase 2 built **one direction**: Dashboard outbox → LinkSpy inbox (`spine_inbox`
+ `spine.py` handlers). LinkSpy has **no outbox**. Sending
`checklist.candidate_created` LinkSpy→Dashboard therefore requires **building the
mirror**: a `spine_outbox` table (in migration 024) + a drain routine on the
existing jobs table that POSTs to a NEW Dashboard inbox endpoint (HMAC, same
`SPINE_SECRET`, same envelope).

---

# PART 2 — The deterministic gap-mapping (versioned, provenance per row)

`FLYWHEEL_MAP_VERSION = 1`. Pure, rule-based (no LLM). Each incident class maps to
the battery check key(s) that would cover it; an empty set = **uncovered** →
draft a candidate.

| incident_class | covering check key(s) | uncovered → candidate (wording · machine_verifiable) |
|---|---|---|
| `finding_broken` | `broken_links` | — |
| `finding_dead_cta` | `broken_links` | — |
| `finding_unverifiable` | `broken_links` | — |
| `sentinel_ssl` | `ssl_valid`, `ssl_expiry` | — |
| `sentinel_domain` | `domain_expiry` | — |
| `sentinel_uptime` | `uptime` | — |
| `perf_regression` | `page_load_time` | — |
| `tracking_missing` | `ga4_installed`, `gtm_setup`, `pixel_present` | — |
| `forms_broken` | `forms_submit` | — |
| `sentinel_indexability` | *(none)* | "Search-engine indexability (robots.txt / noindex / sitemap) re-verified at launch" · **machine_verifiable** (sentinel probes it; not yet a battery key → promoted_unimplemented) |
| `watchdog_thirdparty` | *(none)* | "Critical third-party embeds (chat, pixels, widgets) confirmed loading at launch" · not machine-verifiable (manual) |
| `ads_dead_destination` | *(none)* | "Live ad destinations verified reachable at launch" · **machine_verifiable** (ads-guard checks it; not a battery key → promoted_unimplemented) |

**Gap verdict** (deterministic):
- **covered + passed at delivery** → `drift` (the world changed post-launch) —
  timeline note only, NO candidate.
- **covered + NA/missed at delivery** → `process` finding — timeline note
  "existing check {key} was NA/missed at delivery", NO candidate.
- **uncovered** → `uncovered` → draft a `checklist_candidate` from the template
  above (evidence = incident summary + refs).

"Passed at delivery" is read from the deliverable's `qa_prefills` for the
covering key (holding = passed). No deliverable/prefill → treated as `process`
(can't prove it passed). Nothing here reads or writes anything keyed to a
developer (rule 10).

---

## Build plan
- **Part A (LinkSpy):** migration 024 (`checklist_candidates`, `catalog_versions`,
  `spine_outbox`); the pure classifier (`flywheel.py`); hook the resolution path
  (gated by `FLYWHEEL`); a `spine_outbox` drain job → new Dashboard inbox;
  absorption handler for `checklist.item_promoted`. Contract: add
  `checklist.candidate_created` + `checklist.item_promoted`, bump checksum (both
  repos).
- **Part B (Dashboard):** `ChecklistCandidate` model + `checklist.candidate_created`
  inbox; the Candidates review queue; the human PROMOTE (rationale mandatory) →
  template item + `checklist.item_promoted` via the existing outbox; DISMISS.
- **Part C:** flywheel counters on `/api/admin/spine/stats`; a provenance line on
  flywheel-origin template items.

---

# CONTINUATION — remaining work in build order (zero-archaeology pickup)

**Already shipped** (branch `feat/flywheel-gap`, DRAFT PR, base `main`): the pure
classifier `backend/flywheel.py`, migration `backend/migrations/024_flywheel.sql`
(NOT applied — inert until the wiring lands), contract v2
`backend/spine_contract.py` (checksum `36924adb`), tests `tests/test_flywheel.py`.
Everything below is NOT built yet.

## A-wiring (LinkSpy, `feat/flywheel-gap` — code only, no live DB action)

1. **DB helpers → `backend/database.py`** (async + `_get_client`, `_tables_missing`
   guard returning a NOT_PROVISIONED-style sentinel so pre-024 = no crash):
   - `candidate_create(incident_ref, incident_class, check_key, wording, evidence, machine_verifiable)` → insert `checklist_candidates` (status `draft`), return row.
   - `candidate_by_ref(id)`, `candidate_set_status(id, status, at_col)`.
   - `spine_outbox_add(type, payload)` → insert `spine_outbox`.
   - `spine_outbox_undelivered(limit=20)`, `spine_outbox_mark_delivered(id)`, `spine_outbox_mark_failed(id, err)`.
   - `catalog_version_add(check_key, added_via, source_candidate_ref, active, note)`, `catalog_versions_flywheel()` (for Part C counts).
   - *Test:* none (thin DB glue) — covered via the handler tests with monkeypatch.

2. **Resolution hook → `backend/flywheel.py`** add
   `async def on_incident_resolved(incident_ref, incident_class, deliverable_id=None)`:
   - Guard `os.getenv("FLYWHEEL") != "1"` → return (no-op). **Snapshot-test byte-identical when off.**
   - Resolve delivery state: if `deliverable_id`, read `qa_prefills` for the covering key(s) → `covered_passed = any(verdict=="holding")`; else `None`.
   - `classify_gap(incident_class, covered_passed)`:
     - `uncovered` → `candidate_create(...)` from `res["candidate"]`; then `spine_outbox_add(EVENT_TYPES["CANDIDATE_CREATED"], {candidate_id, incident_class, proposed_check_key, proposed_wording, evidence_summary, machine_verifiable})`; `candidate_set_status(id,"sent","sent_at")` happens on drain, not here.
     - `drift`/`process` → `timeline_add(site, deliverable, "flywheel.gap_"+verdict, {...}, source="flywheel")` — NO candidate.
   - **Call site:** hook `verify_finding` success path (`main.py:~1448`, after `mark_finding_verified`) with `incident_class="finding_"+bucket`; and the sentinel restore path (`sentinel_incidents.restored_at`) with `incident_class="sentinel_uptime"`. Wrap in try/except; best-effort.
   - *Tests* `tests/test_flywheel_wiring.py`: uncovered→candidate row + outbox row (monkeypatch db); covered-passed→timeline note only; `FLYWHEEL` off→no db calls.

3. **Outbox drain job → `backend/spine.py`** `@handler("spine_outbox_drain")`:
   - Fetch `spine_outbox_undelivered(20)`; for each, build the envelope, `sign(raw, SPINE_SECRET)`, POST to `{QA_APP_URL}/api/spine/inbox`; 2xx→`mark_delivered` (+ `candidate_set_status "sent"`); else `mark_failed`. Enqueue on a schedule in `main.py` lifespan (interval like the other routines), gated by `SPINE_SECRET` presence.
   - *Test:* drain marks delivered on 2xx / failed on non-2xx (monkeypatch httpx + db).

4. **Absorption → `backend/main.py` spine inbox endpoint**: add an
   `EVENT_TYPES["ITEM_PROMOTED"]` branch: `absorption_outcome(check_key, machine_verifiable)`
   → `activated` = `catalog_version_add(key,"flywheel",candidate_ref,active=True)`;
   `promoted_unimplemented` = `catalog_version_add(..., active=False, note=...)` + Slack
   ("promoted check {wording} needs a new battery probe — manual follow-up");
   `manual` = timeline note only. Idempotent (inbox already dedupes by event id).
   - *Tests:* each branch; idempotent event → single catalog row.

## Part B (Dashboard, new branch `feat/flywheel-queue`)

1. **Dump (T3) → drift (T2) → prisma migration** (`db:deploy`): model
   `ChecklistCandidate(id, linkspyCandidateRef @unique, incidentClass,
   proposedWording, evidence Json, machineVerifiable Bool, status
   draft|promoted|dismissed @default(draft), rationale?, decidedBy?, decidedAt?,
   createdAt)`. Additive, footered.
2. **Inbox → `src/app/api/spine/inbox/route.ts`** (or extend the existing one):
   handle `checklist.candidate_created` — HMAC verify (contract v2), idempotent by
   `linkspyCandidateRef` → upsert `ChecklistCandidate`. Mirror `spine-contract.ts`
   to v2 (add the two event types; checksum `36924adb`).
3. **Queue UI** `src/app/dashboard/checklists/candidates/page.tsx` (nav near
   Checklists): verdict-first header ("N candidates awaiting review" / empty state
   "No candidates — production hasn't taught us anything new lately"); per-candidate
   card = editable wording, incident-class chip, evidence + **signed handoff link**
   to the LinkSpy incident, machine-verifiable badge, PROMOTE (mandatory rationale)
   / DISMISS (optional reason). No emoji client-side; mono numerals.
4. **Promote action** `.../candidates/actions.ts` (`"use server"`, the ONLY
   template write, T4): insert a `ChecklistTemplateItem` (category from the
   candidate or a "Flywheel" category + the wording as `name`) into the default
   template; set `status=promoted, rationale, decidedBy=session, decidedAt`; emit
   `checklist.item_promoted` via the existing Dashboard outbox (`spine-emit`).
   DISMISS = status+reason only, no emit.
   - *Tests* (`node:test`): inbox idempotency; promote rejects empty rationale;
     template gains item + existing `QACheckItem` untouched (snapshot); dismiss
     emits nothing; source-scan: candidate writes never touch `QACheckItem`.

## Part C (both repos, small)

1. **LinkSpy** `main.py` `/api/admin/spine/stats`: add `candidates_drafted`
   (count status in draft/sent), `candidates_promoted`, `catalog_items_from_flywheel`
   (`catalog_versions where added_via='flywheel'`). *Test:* counters shape.
2. **Dashboard** Checklists template view: a quiet line on flywheel-origin items
   ("added from production incident · {date}"). Needs a provenance marker on the
   template item — since `ChecklistTemplateItem` has no origin column, add a
   NULLABLE `origin?` + `originAt?` in the Part B migration (additive) and set it
   on promote. *Test:* line renders only when `origin='flywheel'`.

## Order to build: A-wiring (1→4) → Part B (1→4) → Part C. Then force one full
loop end-to-end (resolve test incident → candidate → drain → queue → promote →
drain → catalog absorption → counters).
