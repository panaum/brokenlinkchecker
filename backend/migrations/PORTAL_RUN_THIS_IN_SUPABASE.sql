-- ═══════════════════════════════════════════════════════════════════════════
--  CLIENT PORTAL — run this ONCE in the Supabase SQL editor.
--
--  It is the whole database side of arming the portal:
--    1. creates the tenancy tables (workspaces / clients / memberships /
--       invites / audit_log) + adds workspace_id/client_id to sites,
--    2. BACKFILLS: one "Apexure" workspace, attaches every existing site to it,
--       and makes anaum.pandit@apexure.com the owner,
--    3. also creates the share_tokens table (fixes "Share report").
--
--  Safe to run more than once (idempotent). Nothing here changes your current
--  behavior — the portal only enforces once you set PORTAL_ENFORCE=on on Railway.
--
--  After this, on Railway set two env vars:
--     BACKEND_AUTH_SECRET = <any long random string>   (or reuse NEXTAUTH_SECRET)
--     PORTAL_ENFORCE      = on
-- ═══════════════════════════════════════════════════════════════════════════

-- ── 1. Tenancy tables ────────────────────────────────────────────────────────
create table if not exists workspaces (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    owner_email text not null,
    created_at timestamptz not null default now()
);

create table if not exists clients (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces (id) on delete cascade,
    name text not null,
    created_at timestamptz not null default now()
);
create index if not exists clients_workspace_idx on clients (workspace_id);

create table if not exists memberships (
    id uuid primary key default gen_random_uuid(),
    user_email text not null,
    workspace_id uuid not null references workspaces (id) on delete cascade,
    role text not null default 'member',
    client_id uuid references clients (id) on delete cascade,
    created_at timestamptz not null default now(),
    unique (user_email, workspace_id)
);
create index if not exists memberships_email_idx on memberships (user_email);

create table if not exists invites (
    token text primary key,
    workspace_id uuid not null references workspaces (id) on delete cascade,
    client_id uuid references clients (id) on delete cascade,
    email text not null,
    role text not null default 'client_viewer',
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    accepted_at timestamptz,
    revoked boolean not null default false
);
create index if not exists invites_email_idx on invites (email);

create table if not exists audit_log (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid references workspaces (id) on delete set null,
    user_email text not null,
    action text not null,
    site_id uuid,
    at timestamptz not null default now()
);
create index if not exists audit_log_workspace_idx on audit_log (workspace_id, at desc);

alter table sites add column if not exists workspace_id uuid references workspaces (id) on delete set null;
alter table sites add column if not exists client_id uuid references clients (id) on delete set null;
create index if not exists sites_workspace_idx on sites (workspace_id);

-- share_tokens (fixes "Share report → storage unavailable")
create table if not exists share_tokens (
    token text primary key,
    scan_id uuid references scans (id) on delete cascade,
    site_id uuid references sites (id) on delete set null,
    url text not null default '',
    created_at timestamptz not null default now(),
    revoked boolean not null default false
);
create index if not exists share_tokens_scan_idx on share_tokens (scan_id);

-- ── 2. RLS: enable + a PERMISSIVE policy per table. The backend uses the anon
--       key (like every other table here), so authorization is enforced in the
--       app layer, not by RLS. (A deny-by-default policy would lock the backend
--       out — that was a bug.) Drops any prior deny-all policy.
do $$
declare t text;
begin
    foreach t in array array['workspaces','clients','memberships','invites','audit_log']
    loop
        execute format('alter table %I enable row level security', t);
        execute format('drop policy if exists %I on %I', t||'_deny_all', t);
        if not exists (select 1 from pg_policies where schemaname='public' and tablename=t and policyname=t||'_all') then
            execute format('create policy %I on %I for all to public using (true) with check (true)', t||'_all', t);
        end if;
    end loop;
    -- share_tokens is permissive (public read behind a capability token).
    execute 'alter table share_tokens enable row level security';
    if not exists (select 1 from pg_policies where schemaname='public' and tablename='share_tokens' and policyname='share_tokens_all') then
        create policy share_tokens_all on share_tokens for all to public using (true) with check (true);
    end if;
end $$;

-- ── 3. BACKFILL — one Apexure workspace, attach all sites, seed the owner ─────
insert into workspaces (name, owner_email)
select 'Apexure', 'anaum.pandit@apexure.com'
where not exists (select 1 from workspaces where name = 'Apexure');

update sites
set workspace_id = (select id from workspaces where name = 'Apexure' limit 1)
where workspace_id is null;

insert into memberships (user_email, workspace_id, role)
select 'anaum.pandit@apexure.com', (select id from workspaces where name = 'Apexure' limit 1), 'owner'
where not exists (
    select 1 from memberships m
    where m.user_email = 'anaum.pandit@apexure.com'
      and m.workspace_id = (select id from workspaces where name = 'Apexure' limit 1)
);

-- Done. Verify:
--   select count(*) from sites where workspace_id is not null;   -- should be all your sites
--   select * from memberships;                                   -- you as owner
