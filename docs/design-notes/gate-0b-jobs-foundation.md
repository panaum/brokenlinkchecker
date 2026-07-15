# Design Note — Gate 0B: Jobs table + worker (LinkSpy)

**Status:** proposed (autonomous mode — build proceeds immediately after this note).
**Branch:** `feat/jobs-foundation` (LinkSpy repo).
**Architecture:** ARCHITECTURE.md v7 §3 (one Postgres-backed `jobs` table, one
worker, everything enqueues) + §8.1 (the enqueue/drain interface is the socket)
+ §11 (routines are jobs). **Constitution:** additive-only DDL; dump before any
migration; new pipelines ship in SHADOW mode.

---

## What

One Postgres-backed `jobs` table in LinkSpy's Supabase, one always-on worker in
the existing Railway process, and ONE enqueue function every producer must use.
The first routine (monitoring scans) is migrated onto it in **shadow/dry-run**
mode: the scheduler enqueues jobs AND the legacy path still scans; enqueued jobs
execute as no-ops (log only). No flip this gate.

## Schema (migration 021, additive)

```
jobs(
  id uuid pk, kind text, payload jsonb,
  status text  -- queued | running | done | failed | dead
  idempotency_key text,
  attempts int default 0, max_attempts int default 5,
  run_after timestamptz default now(),
  locked_by text, lease_until timestamptz,
  created_at timestamptz default now(), finished_at timestamptz,
  last_error text
)
unique (kind, idempotency_key)     -- idempotency scoped PER KIND
```
Indexes: `(status, run_after)` for the claim scan; the unique index doubles as
the idempotency guard. Permissive RLS in-migration (anon key), per project
convention. Footered with REVERSIBILITY / DATA AT RISK.

## Claim semantics — `FOR UPDATE SKIP LOCKED`, delivered as an RPC (justified)

LinkSpy's backend talks to Supabase through the **PostgREST client**
(`supabase-py`), not raw SQL — so app code cannot open a transaction and issue
`SELECT … FOR UPDATE SKIP LOCKED`. Rather than bolt on a second DB driver
(psycopg) just for locking, the claim is a **Postgres function shipped in the
migration** and called via `supabase.rpc('jobs_claim', …)`:

```sql
create function jobs_claim(p_worker text, p_lease_seconds int, p_kinds text[])
returns setof jobs as $$
  update jobs j set
    status = 'running', locked_by = p_worker,
    lease_until = now() + make_interval(secs => p_lease_seconds),
    attempts = attempts + 1
  where j.id = (
    select id from jobs
    where ((status = 'queued'  and run_after <= now())
        or (status = 'running' and lease_until < now()))   -- reclaim crashed leases
      and (p_kinds is null or kind = any(p_kinds))
    order by run_after
    for update skip locked
    limit 1)
  returning j.*;
$$ language sql;
```

**Why this is cleaner than app-side locking:** the atomic claim (select-and-lock
+ update + return) happens in ONE round-trip inside the database, where
`SKIP LOCKED` actually lives — no read-then-write race, no advisory-lock
bookkeeping, no second driver. Concurrent workers each get a distinct row or
nothing. Crashed-worker recovery is the same query: a `running` row whose
`lease_until` has passed is claimable again (this is the lease, not a separate
sweeper). Choosing lease-expiry reclaim over a heartbeat means a dead worker
self-heals after `lease_seconds` with zero extra machinery.

## The single enqueue function

`enqueue(kind, payload, *, idempotency_key, max_attempts=5, run_after=None)` —
the ONLY way a row enters `jobs`. Implemented as a supabase `upsert` with
`on_conflict='kind,idempotency_key', ignore_duplicates=True` → a duplicate
(kind, idempotency_key) is a no-op, so at-least-once producers get
exactly-one-row. A repo test greps the codebase and FAILS if any other path
writes to `jobs` (`.table("jobs").insert/upsert`, `INSERT INTO jobs`) outside
the enqueue module — mechanizing §8.1's "business logic never touches the table
directly."

## Retry / backoff / dead

On handler success → `done` (finished_at set, lock cleared). On exception →
`jobs_fail(id, err)`: if `attempts >= max_attempts` → `dead` (last_error kept,
finished_at set); else → back to `queued` with
`run_after = now() + backoff(attempts)` (exponential: `min(300, 2^attempts)`
seconds) and last_error recorded. `dead` is terminal and never auto-retried; the
admin endpoint surfaces the count.

## Concurrency (per-domain)

`jobs_claim` takes `p_kinds` so a worker can scope what it drains. Per-domain
caps (relevant only once real scanning is flipped on) are deferred to the flip:
in shadow/dry-run there is no external load to cap. Documented as a follow-up on
the claim function (add a `and (running_for_domain(payload->>'domain') < cap)`
predicate) — not built now, to keep the shadow surface minimal.

## Worker loop

An asyncio task started in the FastAPI startup (the always-on Railway process):
`rpc('jobs_claim', worker_id, lease, kinds)` → if a job, dispatch by `kind` →
success `complete()` / exception `jobs_fail()`; empty → short sleep. Lease is
renewed by re-claim, not heartbeat. One worker for now (the claim is
concurrency-safe, so scaling later is additive — §8.4 S1).

## Shadow migration of monitoring scans

Behind `JOBS_SHADOW` (env, default OFF). When on, the APScheduler monitoring job
ALSO enqueues `kind='monitoring_scan'` (idempotency_key = `site_id:hour_bucket`)
for each due site; the legacy scheduler path keeps scanning for real. The worker
runs `monitoring_scan` in DRY-RUN: it LOGS "would scan {site}" and completes —
performs NO scan. This proves claim/lease/retry/idempotency at real cadence with
zero behavioural change. **Do not flip** — the live cutover is a separate later
instruction after ~7 clean shadow days.

## Exit tests (asserted against a throwaway local Postgres)

1. **Idempotency:** two `enqueue(same kind, same idempotency_key)` → exactly one
   row; the handler runs once.
2. **Lease reclaim / exactly-once:** claim a job, simulate a kill (never
   complete), advance past `lease_until` → the SAME job is re-claimable,
   `attempts` incremented, and a completing worker runs it to `done` exactly
   once.
3. **Poison:** a handler that always throws → after `max_attempts` the job is
   `dead` with `last_error` set, and OTHER queued jobs still get claimed
   (queue keeps moving).
4. **Restart survival:** queued rows persist across a "restart" (they live in
   Postgres; a fresh worker claims them).

Local Postgres (`initdb` trust-auth cluster on a scratch port, torn down after)
— NOT prod, so no LinkSpy dump is needed for the tests. Applying `021` to LinkSpy
**production** remains gated on a LinkSpy `pg_dump` (Constitution rule 3),
executed by the operator in Supabase; the migration header states this.
