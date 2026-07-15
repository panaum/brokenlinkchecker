# Design Note — Phase 1: The Registry (Seam 1)

**Status:** proposed (autonomous mode — code proceeds after commit).
**Branches:** `feat/registry` (LinkSpy) · `feat/registry-columns` (Dashboard/QA).
**Architecture:** ARCHITECTURE.md v7 §2 Seam 1 (LinkSpy tenancy is the system of
record; it gains `deliverables`; the QA app *annotates* its own entities with
registry IDs and never renames them; `qa_bridge_map` was the embryo) + §12 P1
(deliverables + mapping-at-creation; hygiene pass on-demand only).
**Constitution:** additive-only; mapping = annotation, never mutation; service
keys never client-exposed; staleness over errors.

**Scope guard:** Phase 1 is the registry ONLY — a `deliverables` table, four
read/write API routes, three nullable annotation columns on the QA side, and the
create-form + page-view mapping affordance. **No** event spine, outbox,
auto-fill, or anything Phase 2+.

---

## 1. The `deliverables` model (LinkSpy, migration 022 — NOT applied by me)

```
deliverables(
  id uuid pk default gen_random_uuid(),
  site_id uuid -> sites(id) on delete cascade,
  kind text check (kind in ('page','project','site')),
  name text not null,
  external_ref text,          -- the OTHER app's id for this thing (e.g. QA Page.id)
  url text,
  created_at timestamptz default now(),
  archived_at timestamptz     -- soft-retire; never hard-delete a referenced id
)
unique (site_id, external_ref) where external_ref is not null
```
A deliverable is a registry-side handle onto a thing a peer app owns. `kind`
answers §7 Q1 (page | project | site) with a column. `external_ref` is how the QA
app finds *its* deliverable again (`GET ?external_ref=Page.id`). `archived_at`
(not delete) honors §8.2 "IDs are eternal". Additive, idempotent, RLS like
`sites`, footered. **Applied by the operator in Supabase** (header shouts it).

## 2. API surface (additive routes, all under `/api/registry`)

| Route | Purpose |
|---|---|
| `GET /api/registry/clients?search=` | id, name — the client picker |
| `GET /api/registry/clients/{id}/sites` | id, name, url — the site picker |
| `POST /api/registry/deliverables` | `{site_id, kind, name, external_ref, url}` → created deliverable |
| `GET /api/registry/deliverables?external_ref=` | resolve a QA page back to its deliverable |

**not_provisioned:** if the `deliverables` table doesn't exist yet (022 unapplied)
any route returns **503 `{"registry":"not_provisioned"}`** — never a crash. The
clients/sites reads work regardless (those tables exist); only the deliverables
routes gate on provisioning.

## 3. Auth — reuse the qa-bridge service key (justified)

Registry routes authenticate with the **existing qa-bridge service key**
(`_qa_authenticate` → `qa_key_verify`, sha256-hashed at rest, rotatable,
rate-limited) — the same server-to-server trust boundary the QA app already
crosses for "still true today". Reusing it means: one key for the QA↔LinkSpy
channel, one rotation story, one health panel; no new secret, no new table this
phase. A per-route **scope** (status-only vs registry-write) is a genuinely
useful future refinement, but it's a *new column on `qa_bridge_keys`* — an
additive change we defer rather than smuggle into a "registry-only" phase. Until
then the key is coarse-grained by design, and every registry route still
enforces a valid key + the rate limiter. Writes (`POST deliverables`) require the
same key; the QA app holds it server-side only.

**Workspace scoping:** service keys aren't workspace-bound, and today there is a
single Apexure workspace, so `clients` lists that workspace's clients. Binding a
key to a workspace is another additive future change (a column), noted not built.

## 4. How the QA app maps (Phase 1B, annotation-only)

Three **nullable** columns added via prisma migrate (dump-first, drift-checked):
`Client.registry_client_id`, `Page.registry_deliverable_id`, `Page.registry_site_id`.
- **Mapping-at-creation:** the New Page form gains ONE optional "Link to LinkSpy
  site" search (a Next.js API route proxies the registry with `LINKSPY_API_KEY`
  from env — key NEVER in the client bundle). On save with a site chosen: POST a
  deliverable (`kind='page'`, `external_ref=Page.id`, `url`), store the returned
  id in `registry_deliverable_id` (+ `registry_site_id`). Field skipped ⇒
  byte-identical to today (nullable columns, zero behaviour change).
- **On-demand + unlink:** the page view shows a "Registry" line — linked
  (`Linked to {site} ✓` + Unlink) or `Link to LinkSpy →`. Unlink **nulls the
  local columns only**; it does NOT delete the LinkSpy-side deliverable
  (orphan-tolerated — an eternal id with no back-reference is harmless; a future
  reconcile can archive it). No renames, no merges, no mutation of any existing
  QA field (T4).
- **Graceful degradation:** registry unreachable / 503 → the field renders
  disabled ("registry unavailable — link later"); page creation NEVER blocks on
  the registry. Staleness over errors.

## 5. Exit tests

**LinkSpy:** bad/absent key → 401; deliverables routes when table absent → 503
`not_provisioned`; duplicate `external_ref` for a site → 409; clients/sites lists
shape. **QA:** create with field skipped is byte-identical (snapshot); link →
columns set; unlink → columns null + prior state restored; proxy rejects without
key; `LINKSPY_API_KEY` absent from the client bundle (asserted); unreachable
LinkSpy → disabled field, creation still succeeds.
