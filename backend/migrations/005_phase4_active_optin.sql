-- Phase 4: opt-in active form testing.
--
-- Additive only. One new table. Safe to run more than once.
--
-- A form may be submitted by the active tester ONLY if a row here has
-- enabled = true for it. This is on top of the global ACTIVE_FORM_TESTING flag
-- (an environment variable, default off). Both must be true; there is no way to
-- enable submission for a form the user has not explicitly turned on.
--
-- RLS NOTE (same as the other Phase tables): the backend uses the service_role
-- key, which bypasses RLS. The existing tables define no policies. If you enable
-- RLS on this project, add permissive policies or keep using service_role.
--
-- Apply with: Supabase SQL editor, or `psql -f` against the project database.

create table if not exists active_form_optin (
    id          uuid primary key default gen_random_uuid(),
    site_id     uuid not null references sites (id) on delete cascade,
    form_key    text not null,              -- stable identifier for the form
    test_email  text,                       -- filterable qa+linkspy@ address
    enabled     boolean not null default false,
    updated_at  timestamptz not null default now(),
    unique (site_id, form_key)
);

create index if not exists active_form_optin_site_idx
    on active_form_optin (site_id);
