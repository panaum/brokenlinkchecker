-- Phase 1: issues as the primitive.
--
-- Shifts the model from "scan" to "issue": an issue is a persistent entity with
-- a lifecycle (detected -> open -> fixed | ignored). Scans become observations
-- that reconcile issue state. Supersedes the url-matched `link_issues` table
-- (which has no stable fingerprint, no occurrences, and no ignore state).
--
-- Additive and non-destructive: existing sites/scans/results/findings/
-- link_issues tables are untouched. Issues are DERIVED and backfilled from
-- historical scans (see backend/backfill_issues.py). `link_issues` is retired in
-- a later, separate migration once the new path is verified.
--
-- Text + CHECK is used instead of Postgres ENUM types to match the repo's
-- convention (see findings.status/bucket in 001) and to keep the taxonomy
-- editable without an ALTER TYPE dance.
--
-- Apply with: Supabase SQL editor, or `psql -f` against the project database.
-- Safe to run more than once.

-- ─── issues ──────────────────────────────────────────────────────────────────
-- One row per distinct problem on a site, identified across scans by its
-- fingerprint = hash(normalize(target_url) + normalize(source_page_url)). The
-- same broken target appearing in several regions (nav + hero + footer) is ONE
-- issue with several rows in issue_occurrences — the region lives on the
-- occurrence, not on identity. (See backend/issues.py for the rationale and the
-- one documented deviation from the prompt's fingerprint spec.)
create table if not exists issues (
    id                  uuid primary key default gen_random_uuid(),
    site_id             uuid not null references sites (id) on delete cascade,
    fingerprint         text not null,

    status              text not null default 'open'
                        check (status in ('open', 'fixed', 'ignored')),
    -- Mirrors the checker's bucket taxonomy. ('redirect' is accepted for
    -- forward-compatibility; today the checker emits broken/dead_cta/
    -- unverifiable and treats redirects as informational, not findings.)
    issue_type          text not null
                        check (issue_type in ('broken', 'dead_cta', 'unverifiable', 'redirect')),

    target_url          text not null,
    source_page_url     text not null,
    anchor_text         text,
    -- Primary region (nav | hero | body | sidebar | footer). The full spread is
    -- in issue_occurrences; this is the highest-severity one for at-a-glance.
    region              text,
    builder             text,

    -- Lifecycle anchored to the scans that observed it.
    first_seen_scan_id  uuid references scans (id) on delete set null,
    last_seen_scan_id   uuid references scans (id) on delete set null,
    fixed_at_scan_id    uuid references scans (id) on delete set null,
    ignored_at          timestamptz,

    -- Timestamps too, so an issue's age survives scan-row deletion.
    first_seen_at       timestamptz not null default now(),
    last_seen_at        timestamptz not null default now(),
    fixed_at            timestamptz,

    occurrence_count    int not null default 1,
    -- Phase 5 fills this from the connected GA4 property. Nullable: absent means
    -- "no traffic data", never "zero traffic" — the UI must distinguish them.
    monthly_pageviews   int,

    created_at          timestamptz not null default now(),

    -- The fingerprint is unique per site: this is what lets a scan recognise an
    -- existing issue instead of re-creating it every run.
    unique (site_id, fingerprint)
);

-- "All open issues for a site", the hottest query, stays a partial-index hit.
create index if not exists issues_site_open_idx
    on issues (site_id) where status = 'open';

create index if not exists issues_site_status_idx
    on issues (site_id, status);

create index if not exists issues_last_seen_scan_idx
    on issues (last_seen_scan_id);

-- ─── issue_occurrences ───────────────────────────────────────────────────────
-- One row per place an issue appears: a region + element on a source page. The
-- classic nav + footer pair is two occurrences of one issue.
create table if not exists issue_occurrences (
    id                uuid primary key default gen_random_uuid(),
    issue_id          uuid not null references issues (id) on delete cascade,
    source_page_url   text not null,
    region            text,
    element_selector  text,
    severity          text check (severity in ('high', 'med', 'low')),
    created_at        timestamptz not null default now(),

    -- One occurrence per (place, element) — a re-scan updates, never duplicates.
    unique (issue_id, source_page_url, region, element_selector)
);

create index if not exists issue_occurrences_issue_idx
    on issue_occurrences (issue_id);
