-- Verified Lead Delivery, Wave 2: CRM connections + per-form tracer enrollment.
-- Credentials are stored ENCRYPTED (tracer_crypto.py); the app never persists
-- plaintext. Permissive RLS (backend uses the anon key).

create table if not exists crm_connections (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references sites (id) on delete cascade,
    crm_type text not null,                 -- hubspot | ghl
    credentials_enc text not null,          -- Fernet-encrypted blob, never plaintext
    test_ok boolean,
    test_detail text,                       -- redacted human summary ("token valid · scope ok")
    last_tested_at timestamptz,
    created_at timestamptz not null default now(),
    unique (site_id, crm_type)
);
create index if not exists crm_connections_site_idx on crm_connections (site_id);

create table if not exists tracer_enrollments (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references sites (id) on delete cascade,
    contract_key text not null,             -- the enrolled form contract
    enabled boolean not null default false, -- operator opt-in for THIS form
    acknowledged boolean not null default false,   -- "I excluded the test pattern from automations"
    acknowledged_by text,
    acknowledged_at timestamptz,
    test_email text not null,               -- the unmistakably-flagged tracer address
    marker_field text,                      -- designated field carrying the fixed marker
    dry_run_passed boolean not null default false, -- first-run setup-validation gate
    schedule_active boolean not null default false, -- daily schedule armed only after dry-run + confirm
    created_at timestamptz not null default now(),
    unique (site_id, contract_key)
);
create index if not exists tracer_enrollments_site_idx on tracer_enrollments (site_id);

alter table crm_connections enable row level security;
alter table tracer_enrollments enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where tablename='crm_connections' and policyname='crm_connections_all') then
        create policy crm_connections_all on crm_connections for all to public using (true) with check (true); end if;
    if not exists (select 1 from pg_policies where tablename='tracer_enrollments' and policyname='tracer_enrollments_all') then
        create policy tracer_enrollments_all on tracer_enrollments for all to public using (true) with check (true); end if;
end $$;
