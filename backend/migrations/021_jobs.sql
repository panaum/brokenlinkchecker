-- 021_jobs.sql — the one Postgres-backed jobs table + claim/complete/fail RPCs.
-- ARCHITECTURE.md v7 §3 (one jobs table, one worker, everything enqueues).
--
-- ⚠️ DUMP-BEFORE-MIGRATE (Constitution rule 3): before running this in the
--    Supabase SQL editor, take a LinkSpy pg_dump (see docs/runbooks/backup.md)
--    to C:\backups\linkspy-prod-<date>.dump and record the filename in the PR.
--    No dump, no migration.
--
-- Additive only: creates one new table + three functions + indexes + one RLS
-- policy. Touches no existing table. Idempotent (if not exists / or replace).

create table if not exists jobs (
    id uuid primary key default gen_random_uuid(),
    kind text not null,
    payload jsonb not null default '{}'::jsonb,
    status text not null default 'queued',        -- queued | running | done | failed | dead
    idempotency_key text not null,
    attempts integer not null default 0,
    max_attempts integer not null default 5,
    run_after timestamptz not null default now(),
    locked_by text,
    lease_until timestamptz,
    created_at timestamptz not null default now(),
    finished_at timestamptz,
    last_error text
);

-- Idempotency is scoped PER KIND: one (kind, idempotency_key) => one job.
create unique index if not exists jobs_kind_idem_idx on jobs (kind, idempotency_key);
-- The claim scan: cheapest path to the next runnable row.
create index if not exists jobs_claim_idx on jobs (status, run_after);

alter table jobs enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where tablename='jobs' and policyname='jobs_all') then
        create policy jobs_all on jobs for all to public using (true) with check (true); end if;
end $$;

-- ── Atomic claim: SELECT … FOR UPDATE SKIP LOCKED, flip to running, return it.
--    Called via supabase.rpc('jobs_claim', …). Also reclaims crashed leases
--    (running rows whose lease_until has passed). p_kinds NULL = any kind.
create or replace function jobs_claim(p_worker text, p_lease_seconds integer, p_kinds text[] default null)
returns setof jobs as $$
    update jobs j set
        status = 'running',
        locked_by = p_worker,
        lease_until = now() + make_interval(secs => p_lease_seconds),
        attempts = j.attempts + 1
    where j.id = (
        select id from jobs
        where (
                (status = 'queued'  and run_after <= now())
             or (status = 'running' and lease_until is not null and lease_until < now())
              )
          and (p_kinds is null or kind = any(p_kinds))
        order by run_after
        for update skip locked
        limit 1
    )
    returning j.*;
$$ language sql;

-- ── Success: mark done, clear the lock.
create or replace function jobs_complete(p_id uuid)
returns setof jobs as $$
    update jobs set
        status = 'done', finished_at = now(), locked_by = null, lease_until = null
    where id = p_id
    returning *;
$$ language sql;

-- ── Failure: retry with exponential backoff until max_attempts, then dead.
--    (attempts was already incremented at claim time.)
create or replace function jobs_fail(p_id uuid, p_error text)
returns setof jobs as $$
    update jobs set
        status     = case when attempts >= max_attempts then 'dead' else 'queued' end,
        run_after  = case when attempts >= max_attempts then run_after
                          else now() + make_interval(secs => least(300, power(2, attempts)::int)) end,
        finished_at = case when attempts >= max_attempts then now() else null end,
        last_error = p_error,
        locked_by  = null,
        lease_until = null
    where id = p_id
    returning *;
$$ language sql;

-- REVERSIBILITY: additive only. Undo (if ever needed, requires an ADR per
--   Constitution rule 1 because it involves DROPs): drop function jobs_fail,
--   jobs_complete, jobs_claim; drop table jobs. No existing object is altered,
--   so reverting cannot affect any other data.
-- DATA AT RISK: none, additive only. New table + functions + indexes + policy;
--   zero rows touched in any pre-existing table.
