-- Gate 0B exit tests — asserted against a real Postgres (not vibed).
-- Run AFTER applying migrations/021_jobs.sql to the target DB:
--   psql "$URL" -v ON_ERROR_STOP=1 -f migrations/021_jobs.sql
--   psql "$URL" -v ON_ERROR_STOP=1 -f tests/jobs_exit_tests.sql
-- Any RAISE EXCEPTION aborts psql with a non-zero exit → the test fails.

\set ON_ERROR_STOP on
set client_min_messages = notice;

-- clean slate for reruns
delete from jobs where kind like 't_%';

-- TEST 1 — idempotency: duplicate enqueue (same kind, idempotency_key) => 1 row.
insert into jobs (kind, idempotency_key) values ('t_idem','k1') on conflict (kind, idempotency_key) do nothing;
insert into jobs (kind, idempotency_key) values ('t_idem','k1') on conflict (kind, idempotency_key) do nothing;
do $$ begin
  if (select count(*) from jobs where kind='t_idem' and idempotency_key='k1') <> 1 then
    raise exception 'TEST1 FAILED: duplicate enqueue produced % rows',
      (select count(*) from jobs where kind='t_idem'); end if;
  raise notice 'PASS 1 — idempotency: duplicate enqueue -> single row';
end $$;

-- TEST 2 — claim + lease reclaim + exactly-once (kill-worker-mid-job).
insert into jobs (kind, idempotency_key) values ('t_claim','k1') on conflict do nothing;
do $$
declare j jobs; j2 jobs; jid uuid;
begin
  select * into j from jobs_claim('w1', 60, array['t_claim']) limit 1;
  if j.id is null then raise exception 'TEST2 FAILED: nothing claimed'; end if;
  jid := j.id;
  if j.status <> 'running' or j.attempts <> 1 then
    raise exception 'TEST2 FAILED: claimed status=% attempts=%', j.status, j.attempts; end if;
  -- a second worker must NOT get it while the lease is live
  select * into j2 from jobs_claim('w2', 60, array['t_claim']) limit 1;
  if j2.id is not null then raise exception 'TEST2 FAILED: leased job double-claimed'; end if;
  -- kill worker: lease expires -> reclaimable, attempts increments
  update jobs set lease_until = now() - interval '1 minute' where id = jid;
  select * into j2 from jobs_claim('w2', 60, array['t_claim']) limit 1;
  if j2.id <> jid then raise exception 'TEST2 FAILED: expired-lease job not reclaimed'; end if;
  if j2.attempts <> 2 then raise exception 'TEST2 FAILED: attempts=% after reclaim (want 2)', j2.attempts; end if;
  -- completed exactly once
  perform jobs_complete(jid);
  if (select status from jobs where id=jid) <> 'done' then raise exception 'TEST2 FAILED: not done'; end if;
  raise notice 'PASS 2 — claim/skip-locked + lease reclaim + exactly-once complete';
end $$;

-- TEST 3 — poison job goes dead after max_attempts; queue keeps moving.
insert into jobs (kind, idempotency_key, max_attempts) values ('t_poison','k', 2) on conflict do nothing;
insert into jobs (kind, idempotency_key) values ('t_ok','k') on conflict do nothing;
do $$
declare j jobs; jid uuid; st text;
begin
  -- attempt 1
  select * into j from jobs_claim('w1', 60, array['t_poison']) limit 1;
  jid := j.id;
  perform jobs_fail(jid, 'boom-1');
  if (select status from jobs where id=jid) <> 'queued' then
    raise exception 'TEST3 FAILED: not requeued after attempt 1'; end if;
  update jobs set run_after = now() where id = jid;   -- skip backoff wait for the test
  -- attempt 2 -> reaches max_attempts -> dead
  select * into j from jobs_claim('w1', 60, array['t_poison']) limit 1;
  perform jobs_fail(j.id, 'boom-2');
  select status into st from jobs where id = jid;
  if st <> 'dead' then raise exception 'TEST3 FAILED: expected dead, got %', st; end if;
  if (select last_error from jobs where id=jid) is null then
    raise exception 'TEST3 FAILED: last_error not recorded'; end if;
  -- the queue continues: the healthy job is still claimable
  select * into j from jobs_claim('w2', 60, array['t_ok']) limit 1;
  if j.id is null then raise exception 'TEST3 FAILED: queue stalled (t_ok not claimable)'; end if;
  raise notice 'PASS 3 — poison -> dead (last_error kept) + queue continues';
end $$;

-- TEST 4 — restart survival: a queued job persists and a fresh worker claims it.
insert into jobs (kind, idempotency_key) values ('t_restart','k') on conflict do nothing;
do $$
declare j jobs;
begin
  if (select count(*) from jobs where kind='t_restart' and status='queued') <> 1 then
    raise exception 'TEST4 FAILED: queued job did not survive'; end if;
  select * into j from jobs_claim('worker-after-restart', 60, array['t_restart']) limit 1;
  if j.id is null then raise exception 'TEST4 FAILED: new worker could not claim surviving job'; end if;
  raise notice 'PASS 4 — restart survival: queued job persisted + claimed by new worker';
end $$;

-- cleanup test rows
delete from jobs where kind like 't_%';
