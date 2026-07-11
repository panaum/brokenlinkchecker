-- Client portal: per-client Resources (agency-managed labeled links — the QA
-- certificate, staging URL, Figma, GA dashboard). visible=true shows it in the
-- client portal. Permissive RLS (the app enforces authorization).
create table if not exists client_resources (
    id uuid primary key default gen_random_uuid(),
    client_id uuid not null references clients (id) on delete cascade,
    workspace_id uuid references workspaces (id) on delete cascade,
    title text not null,
    url text not null,
    visible boolean not null default true,
    created_at timestamptz not null default now()
);
create index if not exists client_resources_client_idx on client_resources (client_id);

alter table client_resources enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where schemaname='public' and tablename='client_resources' and policyname='client_resources_all') then
        create policy client_resources_all on client_resources for all to public using (true) with check (true);
    end if;
end $$;
