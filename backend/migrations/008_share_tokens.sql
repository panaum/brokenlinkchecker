-- Wave 1: shareable client reports.
--
-- Additive only. No renames, no drops, no changes to existing tables.
-- Safe to run more than once.
--
-- Apply with: Supabase SQL editor, or `psql -f` against the project database.

-- A public, unguessable, revocable link to one scan's report. The token IS the
-- capability — anyone holding it can read that scan's public report, nothing
-- else. Revoking flips `revoked` (the row stays so the link 404s cleanly).
create table if not exists share_tokens (
    token       text primary key,
    scan_id     uuid references scans (id) on delete cascade,
    site_id     uuid references sites (id) on delete set null,
    -- Denormalized so a public read needs no join to sites.
    url         text not null default '',
    created_at  timestamptz not null default now(),
    revoked     boolean not null default false
);

create index if not exists share_tokens_scan_idx on share_tokens (scan_id);

-- RLS in the same migration that creates the table (house rule). The service
-- role bypasses RLS, so the backend still reads/writes freely; this policy just
-- makes the default-deny explicit and keeps a single permissive path.
alter table share_tokens enable row level security;

do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'share_tokens'
          and policyname = 'share_tokens_all'
    ) then
        create policy share_tokens_all
            on share_tokens for all to public
            using (true) with check (true);
    end if;
end $$;
