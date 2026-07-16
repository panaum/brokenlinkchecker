# Design Note — Phase 2 (Event Spine) + Phase 3 thin slice (pre-fill + confirm)

**Status:** proposed (autonomous — code proceeds after commit).
**Branches:** `feat/spine-outbox` (Dashboard) · `feat/spine-inbox` (LinkSpy) ·
`feat/checklist-prefill` (Dashboard).
**Architecture:** v7 §2 Seam 2 (outbox/inbox + HMAC), §4 flagship flow incl. the
READY-GATE correction, §9 guardrails (reconciliation, heartbeat), §10
closing-certificate, §12 P2/P3. **Constitution:** additive-only; shadow-first
(all new pipelines behind flags DEFAULT OFF); machine results NEVER land in a
human QA row without a human click that stamps provenance (T4); keys server-side.

## Shared contract (Phase 2A)
`src/lib/spine-contract.ts` (Dashboard) ≡ `backend/spine_contract.py` (LinkSpy),
both stamped `CONTRACT_CHECKSUM = 175499b1…c57c9d`.
- **Envelope:** `{id (uuid), type, schema_version:1, occurred_at, producer,
  registry_deliverable_id?, registry_site_id?, payload{}}`.
- **Types v1 (only these three):** `deliverable.ready_for_qa`
  `{qa_page_ref, url, name}` · `qa.completed`
  `{qa_page_ref, checklist_summary{passed,failed,na}}` · `heartbeat` `{}`.
- **HMAC:** `hex(hmac_sha256(SPINE_SECRET, raw_body))`, header
  `X-Spine-Signature`; `X-Spine-Sent-At` (unix seconds), reject skew > 300s.
  Signed/verified over the RAW body bytes.

## Trigger mapping — DIAGNOSED against the QA app's real model

The QA app's enums (`src/lib/constants.ts`):
`Status = IN_PROGRESS | IN_QA | LIVE` (on `Page`); `CertStatus = IN_PROGRESS |
PASS | FAIL` (on `QACertificate`).

- **`deliverable.ready_for_qa`** ← a `Page.status` transition **into `IN_QA`**.
  This IS the §4 human-confirmed ready-gate (a dev/lead moving the page into QA).
  Emitting sources: `setPageStatus` (inline) and `savePage` (edit form). NOT
  emitted on `IN_PROGRESS`/`LIVE`, and NOT on a no-op (status already `IN_QA`).
- **`qa.completed`** ← a `QACertificate.status` transition from `IN_PROGRESS`
  **into `PASS` or `FAIL`** (`setCertStatus`). This is the §10 closing-certificate
  sign-off; `completedAt` is already stamped there. `checklist_summary` counts
  `QACheckItem.result` (PASSED/FAILED/NA) for that cert.
- **Emit gate:** only for **registry-linked** pages (`registryDeliverableId`
  set) — an unmapped page has no deliverable for LinkSpy to act on. The envelope
  carries `registry_deliverable_id` + `registry_site_id`.

Rejected alternatives: `Page.status → LIVE` as "completed" (fires after the
cert, loses the checklist summary moment); cert-item edits as "ready" (too noisy,
not the human ready-gate).

## Phase 2B — QA outbox (Dashboard, `feat/spine-outbox`)
- Additive `SpineOutbox` table (Prisma migrate, dump-first, drift-checked).
- **Emit-in-transaction:** inside the SAME `db.$transaction` as the status write,
  insert the outbox row. Gated by `SPINE_EMIT` (unset/0 = byte-identical today —
  snapshot-tested).
- **Drain:** `POST /api/spine/drain` (cron-secret header) — ≤20 undelivered rows,
  POST each to `{LINKSPY_API_URL}/api/spine/inbox` with HMAC, mark `deliveredAt`
  on 2xx, else `attempts++`/`lastError` (retry next drain; no dead state in v1).
  Emits a `heartbeat` if none delivered in 55 min. `vercel.json` cron every 5 min.

## Phase 2C — LinkSpy inbox (LinkSpy, `feat/spine-inbox`, migration WRITTEN not applied)
- `023_spine.sql` (operator-applied, dump-first, additive, footered):
  `spine_inbox` (id = event id, idempotency), `client_timeline`, `qa_prefills`
  (machine results live HERE — never any QA-app table, T4).
- `POST /api/spine/inbox`: verify HMAC+skew → upsert by event id (dup → 200
  `{"duplicate":true}`) → write `client_timeline` → if `ready_for_qa` AND
  `SPINE_CONSUME=1`: enqueue (the ONE existing enqueue fn) a `qa_battery` job,
  idempotency key = event id. `SPINE_CONSUME` off = record only (shadow).
  `heartbeat` → update a heartbeat marker, never enqueue.
- `qa_battery` handler (registered like `monitoring_scan`): resolve deliverable →
  run the EXISTING qa-bridge check catalog against its URL (no new probes) →
  write `qa_prefills` rows with honest verdicts (unverifiable ≠ failing).
- **Routines** (via the jobs table): `heartbeat_watch` hourly (Slack once if
  >2h silent); `reconcile` nightly — compare QA outbox-status vs inbox-processed,
  Slack a summary of stuck rows. **v1 = detect+alert; auto-replay deferred.**
- **Health:** `/api/admin/spine/stats` (last_event_received_at, last_heartbeat_at,
  inbox counts, prefill runs); QA `/api/spine/health` (undelivered count, last drain).

## Phase 3 thin slice — checklist pre-fill + human confirm (Dashboard, `feat/checklist-prefill`)
- Additive NULLABLE `QACheckItem` columns: `machineVerdict`, `machineDetail`,
  `machineCheckedAt`, `confirmedSource ('machine'|'human')`, `confirmedBy`,
  `confirmedAt`. **Written ONLY by the human-confirm action** — never by
  background code (T4).
- Server-side fetch of LinkSpy `GET /api/qa-bridge/prefills?deliverable_id=`
  (new, reads latest `qa_prefills` per check_key), 15-min cache, staleness over
  errors.
- Render (internal checklist only, §10): a quiet "machine-verified: PASS —
  {detail} · {time}" line per mapped item; unmapped items untouched. Results >1h
  old → "refresh checks" (re-enqueue `qa_battery`, rate-limited 1/10min/deliverable).
- **Confirm** (per-item + "Confirm all machine-passed"): ON CLICK ONLY, writes
  the human field AND stamps `confirmedSource='machine'`, `confirmedBy`,
  `confirmedAt`. Unconfirmed machine lines change nothing (snapshot-tested).

## Activation (all flags DEFAULT OFF; operator flips — see final report runbook)
`SPINE_EMIT` (QA), `SPINE_SECRET` (both, same value), `SPINE_CONSUME` (LinkSpy).
Shadow watch 24–48h (events flow, timeline/inbox fill, nothing consumed) before
`SPINE_CONSUME=1`.
