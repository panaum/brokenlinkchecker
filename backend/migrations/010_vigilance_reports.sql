-- Wave 1: persisted monthly vigilance reports. Permissive RLS (app enforces auth).
create table if not exists vigilance_reports (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references sites (id) on delete cascade,
    period_start timestamptz not null,
    period_end timestamptz not null,
    period_label text not null,
    data_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
create index if not exists vigilance_reports_site_idx on vigilance_reports (site_id, period_start desc);
-- One report per site per period (the schedule's duplicate-fire guard).
create unique index if not exists vigilance_reports_site_period_uidx on vigilance_reports (site_id, period_label);

alter table vigilance_reports enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where schemaname='public' and tablename='vigilance_reports' and policyname='vigilance_reports_all') then
        create policy vigilance_reports_all on vigilance_reports for all to public using (true) with check (true);
    end if;
end $$;
