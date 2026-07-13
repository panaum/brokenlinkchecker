-- Data-Governance Attestation PR3: issued attestation documents.
-- Immutable on issue (content_hash + append-only trigger); tokenized share for
-- the client's legal/procurement recipient. Permissive RLS.
create table if not exists attestations (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references sites (id) on delete cascade,
    period_label text not null,
    period_start timestamptz not null,
    period_end timestamptz not null,
    document jsonb not null,
    content_hash text not null,
    share_token text not null unique,
    agency_name text,
    engine_version integer not null,
    classification_version integer not null,
    issued_at timestamptz not null default now()
);
create index if not exists attestations_site_idx on attestations (site_id, issued_at desc);

create or replace function attestations_append_only() returns trigger as $$
begin raise exception 'attestations are immutable once issued: % is not permitted', tg_op; end;
$$ language plpgsql;
drop trigger if exists attestations_no_mutate on attestations;
create trigger attestations_no_mutate before update or delete on attestations
    for each row execute function attestations_append_only();

alter table attestations enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where tablename='attestations' and policyname='attestations_all') then
        create policy attestations_all on attestations for all to public using (true) with check (true); end if;
end $$;
