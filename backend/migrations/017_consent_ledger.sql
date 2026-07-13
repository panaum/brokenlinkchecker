-- Data-Governance Attestation PR1: the consent ledger (immutable) + enrollments.
-- The ledger is the asset: every render session persisted append-only, stamped
-- with the exact engine + classification-table versions that judged it, so any
-- row is reproducible. History cannot be backfilled — it accrues from first
-- enrollment. Same append-only discipline as tracer_runs. Permissive RLS.

create table if not exists consent_enrollments (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references sites (id) on delete cascade,
    page_url text not null,
    regime text not null,                    -- UK | US | BOTH
    cadence text not null default 'weekly',
    enabled boolean not null default true,
    enrolled_at timestamptz not null default now(),
    unique (site_id, page_url)
);
create index if not exists consent_enrollments_site_idx on consent_enrollments (site_id);

create table if not exists consent_sessions (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references sites (id) on delete cascade,
    page_url text not null,
    regime text not null,                    -- UK | US
    mode text not null,                      -- cold | reject | accept | gpc | optout
    requests jsonb not null default '[]'::jsonb,   -- [{host,url,class,provenance,ms_after_load,pre_consent_ui}]
    cmp jsonb not null default '{}'::jsonb,        -- {detected,vendor,operated,accept_clicks,reject_clicks}
    optout jsonb not null default '{}'::jsonb,
    verdicts jsonb not null default '[]'::jsonb,   -- observations + declared limitations
    screenshots jsonb not null default '[]'::jsonb,
    engine_version integer not null,
    classification_version integer not null,
    created_at timestamptz not null default now()
);
create index if not exists consent_sessions_site_idx on consent_sessions (site_id, created_at desc);
create index if not exists consent_sessions_page_idx on consent_sessions (site_id, page_url, created_at desc);

-- Append-only: the ledger is never mutated or backfilled.
create or replace function consent_sessions_append_only() returns trigger as $$
begin
    raise exception 'consent_sessions is an immutable ledger: % is not permitted', tg_op;
end;
$$ language plpgsql;
drop trigger if exists consent_sessions_no_mutate on consent_sessions;
create trigger consent_sessions_no_mutate
    before update or delete on consent_sessions
    for each row execute function consent_sessions_append_only();

alter table consent_enrollments enable row level security;
alter table consent_sessions enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where tablename='consent_enrollments' and policyname='consent_enrollments_all') then
        create policy consent_enrollments_all on consent_enrollments for all to public using (true) with check (true); end if;
    if not exists (select 1 from pg_policies where tablename='consent_sessions' and policyname='consent_sessions_all') then
        create policy consent_sessions_all on consent_sessions for all to public using (true) with check (true); end if;
end $$;
