-- Phase 5: optional per-site expected tracking ids.
--
-- Additive only. One nullable jsonb column, no renames, no drops. Safe to run
-- more than once.
--
-- Holds a site's own GA4 / Meta Pixel / GTM ids, e.g.
--   {"ga4": "G-ABC123", "meta_pixel": "1234567890", "gtm": "GTM-ABCDE"}
-- When set, the tracking audit flags a scanned page whose ids do not match —
-- a mis-pasted snippet sending data to the wrong account. When null, that one
-- check is skipped; every other tracking check runs regardless.
--
-- This column lives on the existing `sites` table, which already has RLS
-- policies from the initial schema, so no new policy is required. (If your
-- project uses the service_role key from the backend, RLS is bypassed anyway.)
--
-- Apply with: Supabase SQL editor, or `psql -f` against the project database.

alter table sites
    add column if not exists expected_tracking jsonb;
