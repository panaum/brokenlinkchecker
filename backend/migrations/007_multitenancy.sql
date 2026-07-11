-- P0: multi-tenancy foundation (workspaces / clients / memberships / invites).
--
-- Additive and backwards-compatible: new tables + NULLABLE columns on `sites`,
-- so this applies safely BEFORE the backfill runs. No existing row changes
-- behavior until the backfill attaches a workspace_id.
--
-- RLS: every new table gets RLS enabled + an explicit DENY-BY-DEFAULT policy in
-- this same file. The FastAPI service-role client bypasses RLS and remains the
-- authorization boundary (enforced in app code via require_site_access); these
-- policies are defense-in-depth, not the primary control.
--
-- Safe to run more than once.

-- ── Tables ───────────────────────────────────────────────────────────────────
create table if not exists workspaces (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    owner_email text not null,
    created_at  timestamptz not null default now()
);

create table if not exists clients (
    id           uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces (id) on delete cascade,
    name         text not null,
    created_at   timestamptz not null default now()
);
create index if not exists clients_workspace_idx on clients (workspace_id);

create table if not exists memberships (
    id           uuid primary key default gen_random_uuid(),
    user_email   text not null,
    workspace_id uuid not null references workspaces (id) on delete cascade,
    -- owner | member | client_viewer
    role         text not null default 'member',
    -- Set only for client_viewer: the single client whose sites they may read.
    client_id    uuid references clients (id) on delete cascade,
    created_at   timestamptz not null default now(),
    unique (user_email, workspace_id)
);
create index if not exists memberships_email_idx on memberships (user_email);
create index if not exists memberships_workspace_idx on memberships (workspace_id);

create table if not exists invites (
    token        text primary key,
    workspace_id uuid not null references workspaces (id) on delete cascade,
    client_id    uuid references clients (id) on delete cascade,
    email        text not null,
    role         text not null default 'client_viewer',
    created_at   timestamptz not null default now(),
    expires_at   timestamptz not null,
    accepted_at  timestamptz,
    revoked      boolean not null default false
);
create index if not exists invites_email_idx on invites (email);

create table if not exists audit_log (
    id           uuid primary key default gen_random_uuid(),
    workspace_id uuid references workspaces (id) on delete set null,
    user_email   text not null,
    action       text not null,
    site_id      uuid,
    at           timestamptz not null default now()
);
create index if not exists audit_log_workspace_idx on audit_log (workspace_id, at desc);

-- ── sites: the tenancy anchor. Nullable columns, backwards-compatible. ────────
alter table sites add column if not exists workspace_id uuid references workspaces (id) on delete set null;
alter table sites add column if not exists client_id    uuid references clients (id) on delete set null;
create index if not exists sites_workspace_idx on sites (workspace_id);
create index if not exists sites_client_idx on sites (client_id);

-- ── RLS: enable + explicit deny-by-default on every new table. ────────────────
do $$
declare t text;
begin
    foreach t in array array['workspaces','clients','memberships','invites','audit_log']
    loop
        execute format('alter table %I enable row level security', t);
        if not exists (
            select 1 from pg_policies
            where schemaname = 'public' and tablename = t
              and policyname = t || '_deny_all'
        ) then
            -- Deny all access to non-service roles; service_role bypasses RLS.
            execute format(
                'create policy %I on %I for all to public using (false) with check (false)',
                t || '_deny_all', t);
        end if;
    end loop;
end $$;
