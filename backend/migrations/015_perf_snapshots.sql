-- Insight Layer PR2: derived per-scan performance aggregates. RECOMPUTABLE from
-- scans.results_json at any time (see recompute_perf) — a cache, not a source of
-- truth. Permissive RLS (backend uses the anon key).
create table if not exists perf_snapshots (
    scan_id uuid primary key,
    site_id uuid not null references sites (id) on delete cascade,
    scanned_at timestamptz not null,
    p50 integer, p90 integer, sample_count integer not null default 0,
    resource_count integer not null default 0,
    computed_at timestamptz not null default now()
);
create index if not exists perf_snapshots_site_idx on perf_snapshots (site_id, scanned_at);
alter table perf_snapshots enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where tablename='perf_snapshots' and policyname='perf_snapshots_all') then
        create policy perf_snapshots_all on perf_snapshots for all to public using (true) with check (true); end if;
end $$;
