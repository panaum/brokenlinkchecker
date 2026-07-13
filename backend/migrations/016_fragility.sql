-- Insight Layer PR3: fragility scores (derived, recomputable from findings) +
-- per-site client-visibility preference (default OFF — it's a sales instrument).
create table if not exists fragility_scores (
    site_id uuid primary key references sites (id) on delete cascade,
    score integer, band text, factors jsonb not null default '[]'::jsonb,
    metrics jsonb not null default '{}'::jsonb, trend jsonb not null default '[]'::jsonb,
    insufficient boolean not null default false,
    computed_at timestamptz not null default now()
);
create table if not exists fragility_prefs (
    site_id uuid primary key references sites (id) on delete cascade,
    client_visible boolean not null default false
);
alter table fragility_scores enable row level security;
alter table fragility_prefs enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where tablename='fragility_scores' and policyname='fragility_scores_all') then
        create policy fragility_scores_all on fragility_scores for all to public using (true) with check (true); end if;
    if not exists (select 1 from pg_policies where tablename='fragility_prefs' and policyname='fragility_prefs_all') then
        create policy fragility_prefs_all on fragility_prefs for all to public using (true) with check (true); end if;
end $$;
