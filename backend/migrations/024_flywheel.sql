-- ═══════════════════════════════════════════════════════════════════════════
-- 024_flywheel.sql — the Quality Flywheel (Phase 5, LinkSpy).
--
-- ⚠️ OPERATOR-APPLIED, DUMP-FIRST (Constitution rule 3): take a LinkSpy pg_dump
--    (docs/runbooks/backup.md) → C:\backups\linkspy-prod-<date>.dump, verify
--    with pg_restore --list, THEN paste this whole file into the Supabase SQL
--    editor (LinkSpy project) and Run. Additive + idempotent → safe to re-run.
-- ═══════════════════════════════════════════════════════════════════════════

-- Gap-analysis candidates drafted when a resolved incident had no delivery check.
create table if not exists checklist_candidates (
    id uuid primary key default gen_random_uuid(),
    incident_ref text,
    incident_class text not null,
    proposed_check_key text,
    proposed_wording text not null,
    evidence jsonb not null default '{}'::jsonb,
    machine_verifiable boolean not null default false,
    status text not null default 'draft' check (status in ('draft', 'sent', 'promoted', 'dismissed')),
    created_at timestamptz not null default now(),
    sent_at timestamptz,
    resolved_at timestamptz
);
create index if not exists checklist_candidates_status_idx on checklist_candidates (status, created_at desc);

-- Which battery check keys are active, and HOW they entered the catalog (§8.2
-- provenance). added_via ∈ 'builtin' | 'flywheel'; source_candidate_ref ties a
-- flywheel entry back to the candidate that produced it.
create table if not exists catalog_versions (
    id uuid primary key default gen_random_uuid(),
    check_key text not null,
    added_via text not null default 'builtin',
    source_candidate_ref text,
    active boolean not null default true,
    note text,
    created_at timestamptz not null default now()
);
create index if not exists catalog_versions_key_idx on catalog_versions (check_key);

-- The LinkSpy OUTBOX mirror (Phase 2 only built the Dashboard→LinkSpy direction).
-- Rows drained by a jobs routine, POSTed to the Dashboard inbox with HMAC.
create table if not exists spine_outbox (
    id uuid primary key default gen_random_uuid(),
    type text not null,
    payload jsonb not null default '{}'::jsonb,
    delivered_at timestamptz,
    attempts integer not null default 0,
    last_error text,
    created_at timestamptz not null default now()
);
create index if not exists spine_outbox_undelivered_idx on spine_outbox (delivered_at, created_at);

-- Permissive RLS in-migration (anon-key backend), consistent with every table.
do $$
declare t text;
begin
    foreach t in array array['checklist_candidates', 'catalog_versions', 'spine_outbox'] loop
        execute format('alter table %I enable row level security', t);
        if not exists (select 1 from pg_policies where tablename = t and policyname = t || '_all') then
            execute format('create policy %I on %I for all to public using (true) with check (true)', t || '_all', t);
        end if;
    end loop;
end $$;

-- REVERSIBILITY: additive only. Undo (requires an ADR per rule 1 — involves
--   DROPs): drop table spine_outbox, catalog_versions, checklist_candidates.
--   No existing table/column is altered.
-- DATA AT RISK: none, additive only. Three new tables + indexes + policies; zero
--   rows in any pre-existing table are read or written by this migration.
