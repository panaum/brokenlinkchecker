# Runbook — Database backups (both Supabase projects)

**Why this exists:** both Supabase projects are on the **FREE TIER — no
point-in-time recovery (PITR), no automatic downloadable backups.** The dump
you take by hand is the ONLY copy that exists. Per the Data-Safety
Constitution rule 3: **no dump, no migration.** Every migration PR records the
dump filename it was taken against.

> Golden rule: take the dump, verify it is non-empty and restorable-looking,
> record its filename in the PR, THEN migrate. Never the other order.

---

## 0. Projects & connection strings

| Project | App | Repo | Env vars (already present) |
|---|---|---|---|
| QA / Deliverables | Deliverables Dashboard | `panaum/dashboard` | `DIRECT_URL` (5432, direct), `DATABASE_URL` (6543, pooled/pgbouncer) |
| LinkSpy | LinkSpy | `panaum/brokenlinkchecker` | Supabase `DATABASE_URL` / service connection |

**Always dump against the DIRECT connection (port 5432), never the pooled
6543/pgbouncer endpoint** — pgbouncer in transaction mode breaks `pg_dump`.
For the QA project that is `DIRECT_URL`.

---

## 1. Method A — `pg_dump` against the direct connection (the real method)

This is the authoritative backup. Run it from any machine with `pg_dump`
(matching the server's major version, currently PG 15/16) and network access.

```bash
# --- QA / Deliverables Dashboard ---
# Uses DIRECT_URL (port 5432). Custom format (-Fc) = compact + restorable.
STAMP="$(date +%Y%m%d-%H%M%S)"
pg_dump "$DIRECT_URL" \
  --no-owner --no-privileges --format=custom \
  --file="qa-dashboard-${STAMP}.dump"

# Verify it is real (non-trivial size + lists objects):
ls -lh "qa-dashboard-${STAMP}.dump"
pg_restore --list "qa-dashboard-${STAMP}.dump" | head -40
```

```bash
# --- LinkSpy ---
STAMP="$(date +%Y%m%d-%H%M%S)"
pg_dump "$LINKSPY_DIRECT_URL" \
  --no-owner --no-privileges --format=custom \
  --file="linkspy-${STAMP}.dump"
ls -lh "linkspy-${STAMP}.dump"
pg_restore --list "linkspy-${STAMP}.dump" | head -40
```

If you don't have the direct URL handy, build it from the Supabase dashboard:
**Project → Settings → Database → Connection string → URI**, and choose the
**Session/Direct** connection (port **5432**), not the Transaction/pooled one.

**Plain-SQL variant** (human-readable, larger; use if you want to eyeball it):
```bash
pg_dump "$DIRECT_URL" --no-owner --no-privileges --format=plain \
  --file="qa-dashboard-${STAMP}.sql"
```

### Store it safely
- Keep the dump OFF this machine's synced folder if the working tree is
  unreliable (see the OneDrive note in the Gate −1 design note). Copy it to a
  location that is NOT auto-syncing/deleting files, and ideally a second one
  (e.g. a private cloud bucket).
- Dumps are secrets-adjacent (they contain all data). Do **not** commit them
  to git. `*.dump` / `*.sql` backups belong in `.gitignore`.

---

## 2. Method B — Supabase Studio (what the dashboard offers on free tier)

- **Project → Database → Backups.** On the free tier this page shows that
  scheduled/PITR backups are **not available** — it is NOT a substitute for
  Method A. Treat it as informational only.
- Supabase Studio has no one-click "download full backup" on free tier, which
  is exactly why Method A (`pg_dump`) is the runbook of record.

---

## 3. Restore (the reversibility half — how a dump is actually used)

A backup you cannot restore is not a backup. The restore target for a real
incident is a **fresh/scratch database** first (verify), and only then, with
operator sign-off, the affected project.

```bash
# Restore into a SCRATCH database to verify the dump is good:
createdb qa_restore_check
pg_restore --no-owner --no-privileges --dbname="postgresql://.../qa_restore_check" \
  "qa-dashboard-<STAMP>.dump"

# Spot-check row counts against what you expect (e.g. ~231 pages):
psql "postgresql://.../qa_restore_check" -c "select count(*) from \"Page\";"
```

Restoring over a live project is a break-glass action — do it only with the
operator present, against a just-taken fresh dump, and record it as an ADR.

---

## 4. Pre-migration checklist (paste into every migration PR)

```
- [ ] Dump taken (Method A) against the target project
- [ ] Dump filename: __________________________
- [ ] Dump verified: size = _____ , `pg_restore --list` shows expected tables
- [ ] Dump stored off the synced working tree (location: __________)
- [ ] Migration is additive-only (no DROP / rename / type-narrowing)
- [ ] Migration file footered with -- REVERSIBILITY / -- DATA AT RISK
```

---

## 5. Quick reference — what "safe" means here

| Situation | Action |
|---|---|
| About to run ANY migration | Method A dump first, record filename |
| Free-tier, no PITR | The dump IS the recovery plan — there is no undo button |
| Working tree dropping files (OneDrive) | Store dumps outside the synced folder |
| Need to prove a dump is good | `pg_restore --list`, then restore to a scratch DB |
