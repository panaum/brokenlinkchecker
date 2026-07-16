-- ═══════════════════════════════════════════════════════════════════════════
-- 023_spine.sql — Event spine inbox + timeline + machine pre-fills (v7 §2 Seam 2).
--
-- ⚠️  OPERATOR-APPLIED, DUMP-FIRST. NOT applied by tooling.
--     1) Take a LinkSpy pg_dump FIRST (Constitution rule 3) → C:\backups\
--        linkspy-prod-<date>.dump ; verify pg_restore --list.
--     2) Paste into the Supabase SQL editor (LinkSpy project) and Run.
--     Additive + idempotent. Depends on 022 (deliverables) being applied.
-- ═══════════════════════════════════════════════════════════════════════════

-- Inbox — id IS the event id (idempotency). Event ids are the producer's outbox
-- ids (cuid), so TEXT, not uuid.
create table if not exists spine_inbox (
    id text primary key,
    type text not null,
    payload jsonb not null default '{}'::jsonb,
    received_at timestamptz not null default now(),
    processed_at timestamptz,
    status text not null default 'received' check (status in ('received', 'processed', 'failed')),
    last_error text
);

-- The deal-to-renewal river (keyed by registry ids).
create table if not exists client_timeline (
    id uuid primary key default gen_random_uuid(),
    registry_site_id text,
    registry_deliverable_id text,
    type text not null,
    payload jsonb not null default '{}'::jsonb,
    occurred_at timestamptz not null default now(),
    source text
);
create index if not exists client_timeline_deliverable_idx on client_timeline (registry_deliverable_id, occurred_at desc);

-- Machine pre-fills — machine QA results live HERE, never in any QA-app table.
create table if not exists qa_prefills (
    id uuid primary key default gen_random_uuid(),
    deliverable_id uuid not null references deliverables (id) on delete cascade,
    check_key text not null,
    verdict text not null check (verdict in ('holding', 'failing', 'couldnt_verify')),
    detail_plain text,
    evidence_ref text,
    battery_run_at timestamptz not null,
    created_at timestamptz not null default now(),
    unique (deliverable_id, check_key, battery_run_at)
);
create index if not exists qa_prefills_deliverable_idx on qa_prefills (deliverable_id, battery_run_at desc);

-- Small key/timestamp markers (heartbeat, last-event) for health + watch.
create table if not exists spine_markers (
    key text primary key,
    at timestamptz not null default now()
);

-- RLS: permissive in-migration (anon-key backend), same pattern as every table.
do $$
declare t text;
begin
    foreach t in array array['spine_inbox','client_timeline','qa_prefills','spine_markers'] loop
        execute format('alter table %I enable row level security', t);
        if not exists (select 1 from pg_policies where tablename=t and policyname=t||'_all') then
            execute format('create policy %I on %I for all to public using (true) with check (true)', t||'_all', t);
        end if;
    end loop;
end $$;

-- REVERSIBILITY: additive only. Undo (ADR-gated, involves DROPs):
--   drop table qa_prefills, spine_markers, client_timeline, spine_inbox.
--   No existing table/column is altered.
-- DATA AT RISK: none, additive only. Four new tables + indexes + policies; zero
--   rows in any pre-existing table are read or written by this migration.
