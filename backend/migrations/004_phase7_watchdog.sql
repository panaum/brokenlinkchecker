-- Phase 7: third-party watchdog.
--
-- Additive only. Two new tables, no changes to existing ones. Safe to run more
-- than once.
--
-- RLS NOTE (this bit us before): the LinkSpy backend connects with the Supabase
-- SERVICE_ROLE key, which BYPASSES row-level security. The existing tables
-- (sites, scans, scan_snapshots, findings) define no RLS policies for the same
-- reason. These two tables follow that pattern. If you later enable RLS on this
-- project, you must add permissive policies (or keep using service_role), or
-- every read/write from the backend will silently return nothing.
--
-- Apply with: Supabase SQL editor, or `psql -f` against the project database.

-- One row per (third-party host, site). The inventory the watchdog aggregates.
create table if not exists third_party_hosts (
    id              uuid primary key default gen_random_uuid(),
    host            text not null,
    site_id         uuid not null references sites (id) on delete cascade,
    resource_type   text,                       -- script | iframe | form_action
    last_status     text not null default 'unknown',   -- up | down | unknown
    last_status_code integer,
    sample_url      text,
    last_checked_at timestamptz not null default now(),
    unique (host, site_id)
);

create index if not exists third_party_hosts_host_idx
    on third_party_hosts (host);

create index if not exists third_party_hosts_down_idx
    on third_party_hosts (host) where last_status = 'down';

-- One row per host we have alerted about, for the 24h dedupe. A host outage is
-- announced once, not once per site and not again within the window.
create table if not exists watchdog_alerts (
    host            text primary key,
    last_alerted_at timestamptz not null default now()
);
