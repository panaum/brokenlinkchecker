-- QA-bridge ("Still True Today") — LinkSpy exposes live status for QA-app
-- delivery-checklist items. ONE-WAY: QA reads; nothing here is written by QA.
--
-- Two tables:
--   qa_bridge_map   — explicit identity mapping (a QA page ref → a monitored
--                     site, optionally a specific page_url). No name-guessing.
--   qa_bridge_keys  — service API keys for the read-only status endpoint,
--                     HASHED at rest (sha256), rotatable, revocable.
--
-- Permissive RLS in-migration (anon-key backend), consistent with every prior
-- table in this project.

-- ── identity mapping ─────────────────────────────────────────────────────────
create table if not exists qa_bridge_map (
    id uuid primary key default gen_random_uuid(),
    qa_page_ref text not null,                       -- the QA app's page/deliverable id
    linkspy_site_id uuid not null references sites (id) on delete cascade,
    page_url text,                                   -- nullable → page-level precision
    created_by text,
    created_at timestamptz not null default now(),
    unique (qa_page_ref)                             -- one live source per QA ref
);
create index if not exists qa_bridge_map_site_idx on qa_bridge_map (linkspy_site_id);

alter table qa_bridge_map enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where tablename='qa_bridge_map' and policyname='qa_bridge_map_all') then
        create policy qa_bridge_map_all on qa_bridge_map for all to public using (true) with check (true); end if;
end $$;

-- ── service API keys (hashed) ────────────────────────────────────────────────
create table if not exists qa_bridge_keys (
    id uuid primary key default gen_random_uuid(),
    label text,                                      -- human name for the key
    key_hash text not null unique,                   -- sha256 hex of the raw token
    key_prefix text not null,                        -- first 8 chars, for display only
    created_by text,
    created_at timestamptz not null default now(),
    last_used_at timestamptz,
    revoked_at timestamptz                           -- soft-revoke; keeps the audit trail
);
create index if not exists qa_bridge_keys_hash_idx on qa_bridge_keys (key_hash);

alter table qa_bridge_keys enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where tablename='qa_bridge_keys' and policyname='qa_bridge_keys_all') then
        create policy qa_bridge_keys_all on qa_bridge_keys for all to public using (true) with check (true); end if;
end $$;
