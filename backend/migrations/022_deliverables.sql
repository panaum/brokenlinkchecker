-- ═══════════════════════════════════════════════════════════════════════════
-- 022_deliverables.sql — the Registry (ARCHITECTURE.md v7 §2 Seam 1).
--
-- ⚠️  OPERATOR-APPLIED, DUMP-FIRST. This file is NOT applied by tooling.
--     1) Take a LinkSpy pg_dump FIRST (Constitution rule 3):
--          pg_dump against the DIRECT/pooler URL (port 5432) -> C:\backups\
--          linkspy-prod-<date>.dump ; verify with pg_restore --list.
--     2) Paste this whole file into the Supabase SQL editor (LinkSpy project)
--        and Run. It is additive + idempotent, so re-running is safe.
-- ═══════════════════════════════════════════════════════════════════════════

create table if not exists deliverables (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references sites (id) on delete cascade,
    kind text not null check (kind in ('page', 'project', 'site')),
    name text not null,
    external_ref text,                 -- the peer app's id for this thing (e.g. QA Page.id)
    url text,
    created_at timestamptz not null default now(),
    archived_at timestamptz            -- soft-retire; ids are eternal (never hard-deleted)
);

-- One deliverable per (site, external_ref) — the QA app's Page.id maps once.
-- Partial unique index so many rows may have a NULL external_ref.
create unique index if not exists deliverables_site_extref_idx
    on deliverables (site_id, external_ref) where external_ref is not null;
create index if not exists deliverables_site_idx on deliverables (site_id);
create index if not exists deliverables_extref_idx on deliverables (external_ref) where external_ref is not null;

-- RLS consistent with the rest of the schema (anon-key backend → permissive
-- policy in-migration, same pattern as sites/qa_bridge_map/etc.).
alter table deliverables enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where tablename='deliverables' and policyname='deliverables_all') then
        create policy deliverables_all on deliverables for all to public using (true) with check (true); end if;
end $$;

-- REVERSIBILITY: additive only. Undo (requires an ADR per Constitution rule 1,
--   because it involves DROPs): drop table deliverables (cascades its indexes +
--   policy). No existing table/column is altered, so reverting cannot touch any
--   other data.
-- DATA AT RISK: none, additive only. One new table + indexes + one RLS policy;
--   zero rows in any pre-existing table are read or written by this migration.
