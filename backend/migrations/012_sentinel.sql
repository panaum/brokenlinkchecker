-- Wave 3: Disaster Sentinel — SSL/domain expiry, indexability, uptime.
-- Permissive RLS (backend uses the anon key; app enforces auth).
create table if not exists sentinel_status (
    site_id uuid primary key references sites (id) on delete cascade,
    ssl_expiry timestamptz, ssl_issuer text,
    domain_expiry timestamptz,
    robots_ok boolean, meta_noindex boolean, header_noindex boolean, sitemap_ok boolean,
    prev_ssl_days integer, prev_domain_days integer,   -- for change-only alert ladder
    last_checked_at timestamptz
);
create table if not exists uptime_pings (
    id bigserial primary key,
    site_id uuid not null references sites (id) on delete cascade,
    at timestamptz not null default now(),
    up boolean not null
);
create index if not exists uptime_pings_site_idx on uptime_pings (site_id, at desc);
create table if not exists sentinel_incidents (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references sites (id) on delete cascade,
    down_at timestamptz not null default now(),
    restored_at timestamptz
);
create index if not exists sentinel_incidents_site_idx on sentinel_incidents (site_id, down_at desc);

alter table sentinel_status enable row level security;
alter table uptime_pings enable row level security;
alter table sentinel_incidents enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where tablename='sentinel_status' and policyname='sentinel_status_all') then
        create policy sentinel_status_all on sentinel_status for all to public using (true) with check (true); end if;
    if not exists (select 1 from pg_policies where tablename='uptime_pings' and policyname='uptime_pings_all') then
        create policy uptime_pings_all on uptime_pings for all to public using (true) with check (true); end if;
    if not exists (select 1 from pg_policies where tablename='sentinel_incidents' and policyname='sentinel_incidents_all') then
        create policy sentinel_incidents_all on sentinel_incidents for all to public using (true) with check (true); end if;
end $$;
