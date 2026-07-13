-- Inbound-404 triage: imported dead-URL demand (GSC crawl errors or 404 logs).
-- Re-import replaces the current picture per source. Permissive RLS (anon key).
create table if not exists inbound_404_demand (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references sites (id) on delete cascade,
    url_normalized text not null,
    hits integer not null default 0,
    source text not null,                    -- gsc | server_log
    period_start timestamptz, period_end timestamptz,
    top_referrers jsonb not null default '[]'::jsonb,
    last_seen text,
    imported_at timestamptz not null default now(),
    unique (site_id, url_normalized, source)
);
create index if not exists inbound_404_demand_site_idx on inbound_404_demand (site_id, hits desc);
alter table inbound_404_demand enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where tablename='inbound_404_demand' and policyname='inbound_404_demand_all') then
        create policy inbound_404_demand_all on inbound_404_demand for all to public using (true) with check (true); end if;
end $$;
