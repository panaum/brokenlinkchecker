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
