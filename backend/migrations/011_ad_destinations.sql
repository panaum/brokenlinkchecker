-- Wave 2: Google Ads waste-guard. Imported ad destinations + daily verification.
-- Permissive RLS (backend uses the anon key; app enforces auth).
create table if not exists ad_destinations (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references sites (id) on delete cascade,
    campaign text not null default 'Ungrouped',
    ad_group text not null default '',
    final_url text not null,
    cost_per_day numeric,                 -- nullable: only when the export carried cost
    status text not null default 'unchecked',   -- unchecked | ok | broken | unverifiable
    response_ms integer,
    last_checked_at timestamptz,
    breach_since timestamptz,             -- when it first went provably dead (for "since detected")
    imported_at timestamptz not null default now(),
    fingerprint text not null,            -- sha1(campaign|ad_group|final_url)
    unique (site_id, fingerprint)
);
create index if not exists ad_destinations_site_idx on ad_destinations (site_id);

alter table ad_destinations enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where schemaname='public' and tablename='ad_destinations' and policyname='ad_destinations_all') then
        create policy ad_destinations_all on ad_destinations for all to public using (true) with check (true);
    end if;
end $$;
