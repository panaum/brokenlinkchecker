-- Phase 9: continuous monitoring.
--
-- Additive only. One nullable column, no renames, no drops, no changes to
-- existing data. Safe to run more than once.
--
-- The uptime record (status endpoint, weekly digest, healthy-streak) reads
-- entirely from scan_snapshots.totals_json, which already exists — this
-- migration only adds the on/off switch.
--
-- Apply with: Supabase SQL editor, or `psql -f` against the project database.

alter table sites
    add column if not exists monitoring_enabled boolean not null default false;

-- Fast lookup of the sites the scheduler must load on startup.
create index if not exists sites_monitoring_enabled_idx
    on sites (monitoring_enabled)
    where monitoring_enabled;
