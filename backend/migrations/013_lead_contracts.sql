-- Verified Lead Delivery, Wave 1: contracts + the immutable run ledger.
-- The ledger is the moat: append-only, complete from v1, enforced by a DB
-- trigger (not just app code). Permissive RLS (backend uses the anon key).

-- ── form_contracts: what "intact" means for a form. Append-only + versioned:
--    an edit/confirm/archive is a NEW row (version+1); prior versions are never
--    mutated. The live contract for a form = highest version for its key. ──
create table if not exists form_contracts (
    id uuid primary key default gen_random_uuid(),
    site_id uuid not null references sites (id) on delete cascade,
    contract_key text not null,                 -- stable per (site, form_ref) across versions
    version integer not null default 1,
    status text not null default 'draft',       -- draft | confirmed | archived
    form_ref jsonb not null default '{}'::jsonb, -- {page_url, form_id, selector}
    fields jsonb not null default '[]'::jsonb,   -- [{name, required, kind, populated_by, expected_crm_property}]
    destination jsonb not null default '{}'::jsonb, -- {type, ids...}
    events jsonb not null default '[]'::jsonb,   -- [{trigger, name, required_params[]}]
    confirmed_by text,
    confirmed_at timestamptz,
    created_at timestamptz not null default now(),
    unique (contract_key, version)
);
create index if not exists form_contracts_site_idx on form_contracts (site_id);
create index if not exists form_contracts_key_idx on form_contracts (contract_key, version desc);

-- ── tracer_runs: THE LEDGER. Written by Wave 2, one complete row per run,
--    every branch. Append-only: no DELETE ever; the ONLY permitted UPDATE is
--    the cleanup status advancing (pending → done/failed), and never once the
--    row is closed (cleanup='done'). Enforced by trigger below. ──
create table if not exists tracer_runs (
    id uuid primary key default gen_random_uuid(),
    contract_id uuid not null references form_contracts (id),
    contract_version integer not null,
    site_id uuid not null references sites (id) on delete cascade,
    started_at timestamptz not null default now(),
    mode text not null,                          -- dryrun | scheduled | manual
    outcome text,                                -- verified|partial|failed_submit|failed_arrival|failed_cleanup
    submitted_payload_hash text,
    arrival jsonb not null default '[]'::jsonb,   -- [{field, sent_value_hash, crm_property, arrived, arrived_value_matches}]
    crm_contact_ref text,
    cleanup text not null default 'pending',      -- done | failed | pending
    duration_ms integer,
    evidence jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
create index if not exists tracer_runs_contract_idx on tracer_runs (contract_id, started_at desc);
create index if not exists tracer_runs_site_idx on tracer_runs (site_id, started_at desc);

-- ── The append-only enforcement. Blocks DELETE outright; blocks any UPDATE
--    that touches a column other than `cleanup`; blocks even a cleanup change
--    once the row is closed. This is the guarantee the certificate rests on. ──
create or replace function tracer_runs_append_only() returns trigger as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'tracer_runs is append-only: DELETE is not permitted';
    end if;
    -- UPDATE path: only `cleanup` may move, and only while not yet done.
    if (new.id, new.contract_id, new.contract_version, new.site_id, new.started_at,
        new.mode, new.outcome, new.submitted_payload_hash, new.arrival,
        new.crm_contact_ref, new.duration_ms, new.evidence)
       is distinct from
       (old.id, old.contract_id, old.contract_version, old.site_id, old.started_at,
        old.mode, old.outcome, old.submitted_payload_hash, old.arrival,
        old.crm_contact_ref, old.duration_ms, old.evidence)
    then
        raise exception 'tracer_runs is append-only: only the cleanup status may change';
    end if;
    if old.cleanup = 'done' then
        raise exception 'tracer_runs row is closed (cleanup done): no further updates';
    end if;
    return new;
end;
$$ language plpgsql;

drop trigger if exists tracer_runs_no_mutate on tracer_runs;
create trigger tracer_runs_no_mutate
    before update or delete on tracer_runs
    for each row execute function tracer_runs_append_only();

-- ── RLS (permissive; the app layer is the real boundary) ──
alter table form_contracts enable row level security;
alter table tracer_runs enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where tablename='form_contracts' and policyname='form_contracts_all') then
        create policy form_contracts_all on form_contracts for all to public using (true) with check (true); end if;
    if not exists (select 1 from pg_policies where tablename='tracer_runs' and policyname='tracer_runs_all') then
        create policy tracer_runs_all on tracer_runs for all to public using (true) with check (true); end if;
end $$;
