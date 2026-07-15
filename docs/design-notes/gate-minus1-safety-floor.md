# Design Note — Gate −1: Safety Floor

**Status:** proposed — awaiting operator approval (Constitution rule 7).
**Branch:** `chore/data-safety-floor` (QA/Dashboard repo primary; docs also in LinkSpy repo).
**Prime directive:** ZERO data loss / zero data-meaning corruption. Two live
free-tier Supabase DBs, no PITR. One holds ~231 pages of irreplaceable QA
history.

This note is the FIRST deliverable of the gate. No implementation code or DB
operation happens until it is approved. It states what Gate −1 does, what data
is at risk, how every step reverses, and the exit tests.

---

## What Gate −1 does (and does not)

**Goal:** put a safety floor under the QA/Deliverables database *before* any
schema work in later gates — a real backup habit, and a migration tool that
cannot silently mutate production the way `prisma db push` did.

1. **Backup runbook** (`docs/runbooks/backup.md`, BOTH repos) — exact
   `pg_dump` commands for both projects. *(Done in this PR — it's docs.)*
2. **Prisma-migrate conversion** (QA repo) — stop using `prisma db push`;
   baseline the CURRENT production schema as migration `0` and mark it applied
   so Prisma's history matches reality **without executing any DDL**. Add
   `db:migrate` (dev) and `db:deploy` (prod) scripts. Add a guard that fails
   the build if `db push` is invoked or referenced.
3. **ADR-001** (`docs/decisions/001-prisma-migrate-and-additive-ddl.md`) —
   records the decision: migrate (not push) + additive-only DDL +
   dump-before-migrate.

**Explicit non-goals:** no schema changes to either app's real tables (the
only new DB object across the whole gate is Prisma's own `_prisma_migrations`
bookkeeping table); no data movement; nothing consumed or activated.

---

## Data-at-risk analysis (honest)

| Step | Touches production? | Data at risk | Mitigation |
|---|---|---|---|
| Backup runbook (docs) | No | none | — |
| npm scripts + db-push guard | No (repo files) | none | — |
| ADR-001 (docs) | No | none | — |
| `prisma migrate diff` to author baseline SQL | No — offline, reads schema files only | none | baseline SQL is generated, reviewed, NOT run |
| `prisma migrate resolve --applied 0_baseline` | **Yes — one INSERT into `_prisma_migrations`** | none to app data (no DDL runs); risk is *mis-baselining* if schema.prisma has drifted from real prod | **dump first**; before resolving, run `prisma migrate diff` **from the live DB to schema** to PROVE zero drift; if drift exists, STOP and reconcile |
| Exit-test additive migration via `db:deploy` | **Yes — one additive, reversible column/table** | the write itself is additive-only + footered with reversibility; risk is generic "any prod write" | **dump first**; additive-only; documented undo |

**The one real hazard is mis-baselining.** `db push` may have left prod's
actual schema slightly different from `schema.prisma` (e.g. a model added to
the file but never pushed, or vice-versa). If we baseline against the *file*
while prod differs, Prisma will believe a false history and a later migration
could try to "add" something that already exists (or assume something exists
that doesn't). **Guardrail:** before `migrate resolve`, run a live-DB→schema
diff and require it to be EMPTY. A non-empty diff is a STOP, not a warning.

---

## Reversibility story

- Docs / scripts / guard / ADR: `git revert`. Zero prod impact.
- Baseline (`migrate resolve`): reversible by `DELETE`ing the single
  `_prisma_migrations` row — no app data ever touched. (And a dump exists.)
- Exit-test migration: additive column/table, dropped by its documented undo
  (retained per rule 1's deprecation cycle, or dropped since it is a
  throwaway test object created solely to prove `db:deploy` works).
- Whole gate: a dated `pg_dump` is taken first and its filename recorded in
  the PR — the ultimate undo on a no-PITR DB.

---

## Exit tests (all must pass before Gate 0A)

1. `prisma migrate status` against production → **in-sync, zero pending, zero
   drift.**
2. A live-DB→schema `prisma migrate diff` → **empty** (proves the baseline is
   honest, not just self-consistent).
3. One trivial ADDITIVE test migration applied via `db:deploy` → **succeeds**;
   schema diff vs pre-gate state is empty except `_prisma_migrations` (+ the
   throwaway additive object, then reverted).
4. The db-push guard **demonstrably fails** a build that references `db push`.
5. Backup runbook present in BOTH repos; a dated dump exists and its filename
   is recorded in the PR.

---

## Environment risk surfaced (needs an operator decision)

Both repos live under **OneDrive** (`…/OneDrive/Desktop/…`). While preparing
this gate, a just-created file (`architecture.md`) **disappeared from the
working tree** — most likely a OneDrive sync race. On a no-PITR, "the-dump-is-
the-only-copy" footing, a working tree that can silently drop files is itself
a data-safety risk (a dump written there could vanish; a half-written
migration could be corrupted mid-sync).

**Recommendation before any DB work:** either (a) pause OneDrive sync for the
two repo folders during this epic, or (b) work from clones outside the synced
tree. And per the runbook: **store all dumps outside the OneDrive folder.**
`architecture.md` is now committed to git, so it is recoverable regardless.

---

## The STOP (per rule 7 and the dump-first rule)

Awaiting from the operator, before I write any implementation code or run any
DB command:

1. **Approve this design note** (or amend).
2. **Take the QA dump** (Method A in the runbook) and reply with its
   **filename** — OR authorize me to run it, confirming the direct connection
   string is in env and that autonomous execution against production is
   acceptable. I default to operator-runs-the-dump for safety.
3. **Decide the OneDrive question** (pause sync / clone out / accept risk).

On go, I proceed to: author the baseline migration (offline), add the scripts
+ guard, write ADR-001, then run the drift-check → baseline → exit-test
sequence **against the just-dumped DB**, and STOP again with the report.
