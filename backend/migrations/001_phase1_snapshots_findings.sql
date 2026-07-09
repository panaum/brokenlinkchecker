-- Phase 1: baseline diffing.
--
-- Additive only. No renames, no drops, no changes to existing tables.
-- Safe to run more than once.
--
-- Apply with: Supabase SQL editor, or `psql -f` against the project database.

-- One row per completed scan of a site: the baseline a later scan diffs against.
create table if not exists scan_snapshots (
    id          uuid primary key default gen_random_uuid(),
    site_id     uuid not null references sites (id) on delete cascade,
    -- Nullable: a snapshot may outlive the scans row it came from.
    scan_id     uuid references scans (id) on delete set null,
    created_at  timestamptz not null default now(),
    -- Counts plus the fingerprints of every link seen, which backs the
    -- "New Links" card without storing a row per working link.
    totals_json jsonb not null default '{}'::jsonb
);

create index if not exists scan_snapshots_site_created_idx
    on scan_snapshots (site_id, created_at desc);

-- One row per flagged item in a snapshot. Working links are not findings.
create table if not exists findings (
    id            uuid primary key default gen_random_uuid(),
    snapshot_id   uuid not null references scan_snapshots (id) on delete cascade,
    -- Denormalized so "all open findings for a site" is one indexed query.
    site_id       uuid not null references sites (id) on delete cascade,
    -- Stable identity across scans: hash of
    -- (normalized page url, target href, anchor text, kind).
    fingerprint   text not null,
    bucket        text not null,          -- broken | dead_cta | unverifiable
    confidence    text,                   -- high | medium | low
    url           text not null,
    anchor_text   text,
    zone          text,
    reason        text,
    -- Carried forward from the previous snapshot on a recurring finding, so an
    -- issue's age survives a rerun ("broken for 12 days").
    first_seen_at timestamptz not null default now(),
    resolved_at   timestamptz,            -- set when a prior finding disappears
    status        text not null default 'open'   -- open | resolved | verified_fixed
);

create index if not exists findings_site_fingerprint_idx
    on findings (site_id, fingerprint);

create index if not exists findings_snapshot_idx
    on findings (snapshot_id);

create index if not exists findings_site_open_idx
    on findings (site_id) where resolved_at is null;
