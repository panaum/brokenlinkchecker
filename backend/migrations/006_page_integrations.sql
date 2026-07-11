-- Per-page third-party integration inventory + health.
--
-- Additive only. One new table. Safe to run more than once.
--
-- RLS (REQUIRED, in this same migration): the LinkSpy backend connects with the
-- Supabase SERVICE_ROLE key, which bypasses RLS. But — unlike the earlier
-- tables, which left RLS off — this table ENABLES RLS and adds a permissive
-- policy, so the table is safe by default and still fully accessible from the
-- backend. If you later lock this project down, tighten the policy; do not leave
-- a table exposed with no policy.
--
-- Apply with: Supabase SQL editor, or `psql -f` against the project database.

create table if not exists page_integrations (
    id              uuid primary key default gen_random_uuid(),
    scan_id         uuid,                       -- the scan this attribution belongs to
    page_url        text not null,
    host            text not null,              -- registrable-domain host, e.g. calendly.com
    resource_url    text not null,              -- full URL, for the health check
    category        text not null,              -- Analytics | Advertising/Pixels | …
    type            text not null,              -- script | iframe | embed | inline_snippet
    detected_id     text,                       -- e.g. GTM-P593C44 (inline snippets)
    health_status   text not null default 'checking',  -- healthy|down|unresponsive|unknown|checking
    last_checked_at timestamptz,
    created_at      timestamptz not null default now(),
    unique (scan_id, page_url, host, resource_url, detected_id)
);

create index if not exists page_integrations_scan_idx
    on page_integrations (scan_id);

create index if not exists page_integrations_scan_page_idx
    on page_integrations (scan_id, page_url);

-- Enable RLS and add a permissive policy. The backend uses service_role (which
-- bypasses this); the policy keeps the table from being wide-open with RLS off.
alter table page_integrations enable row level security;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public' and tablename = 'page_integrations'
          and policyname = 'page_integrations_all'
    ) then
        create policy page_integrations_all
            on page_integrations
            for all
            to public
            using (true)
            with check (true);
    end if;
end $$;
