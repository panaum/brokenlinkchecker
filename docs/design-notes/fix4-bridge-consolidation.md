# Fix 4 — Bridge consolidation (`qa_bridge_map` ↔ registry `deliverables`)

**Status:** diagnosis complete, Strategy A implemented behind
`QA_BRIDGE_CONSOLIDATION=1` (default OFF). Branch `feat/bridge-consolidation`,
not merged.

---

## 0. Premise correction — read this first

The task framing for this work stated:

> "Every registry-linked page automatically creates a `qa_bridge_mapping` row
> too, per the Phase 1 wiring. So the two tables are populated in parallel."

**Both halves of that are false, and the table name was wrong.** Verified by
grepping every reader and writer in both repos:

| Claim | Reality |
|---|---|
| Table is `qa_bridge_mapping` | Table is **`qa_bridge_map`** (`020_qa_bridge.sql:14`). `qa_bridge_mapping` has zero matches in either repo. |
| Registry linking auto-writes a map row | **It does not.** `registry_create_deliverable` (`main.py:3356-3377`) calls only `registry_insert_deliverable`, which touches `table("deliverables")` and nothing else (`database.py:2913-2922`). |
| The two tables are populated in parallel | **They are populated by two entirely independent flows** that never call each other. |

This matters because it changes the problem from *"tidy up duplicated writes"*
into something more consequential — see §4.

---

## 1. Every reader of `qa_bridge_map`

Three read paths, all in the backend. Nothing in the Dashboard repo touches the
table (or any LinkSpy table) directly — it is HTTP-only across the seam.

| # | Reader | Location | Reached via | Purpose |
|---|---|---|---|---|
| R1 | `_qa_get_map_sync` → `qa_get_map` | `database.py:2623-2637` | `GET /api/qa-bridge/status` (`main.py:3239`) | Resolve one `qa_page_ref` → `{linkspy_site_id, page_url, created_at}` for the "Still True Today" snapshot. **The only production read path.** |
| R2 | `_qa_list_maps_sync` → `qa_list_maps` | `database.py:2607-2620` | `GET /api/sites/{site_id}/qa-bridge/maps` (`main.py:3256-3257`) | Admin listing for `QaBridgePanel.tsx`. Agency-internal UI only. |
| R3 | *(none in Dashboard)* | — | — | Dashboard reads only `GET /api/qa-bridge/status?qa_page_ref=…` over HTTP (`src/lib/linkspy/client.ts:31`). It never sees the table. |

**Consumer of R1 downstream:** `qa_snapshot(site_id, page_url, baseline_at)`
(`database.py:2742,2871`) — needs exactly the three fields the map supplies.

## 2. Every writer of `qa_bridge_map`

| # | Writer | Location | Reached via | Automatic? |
|---|---|---|---|---|
| W1 | `_qa_add_map_sync` → `qa_add_map` (upsert on `qa_page_ref`) | `database.py:2588-2604` | `POST /api/sites/{site_id}/qa-bridge/maps` (`main.py:3263-3269`) | **No — manual only.** Driven by a human in `QaBridgePanel.tsx`. |
| W2 | `_qa_unlink_sync` → `qa_unlink` (delete by id) | `database.py:2640-2654` | `DELETE …/qa-bridge/maps/{map_id}` (`main.py:3279-3280`) | No — manual. |

`qa_add_map` has **exactly one caller** in the entire codebase (`main.py:3269`).
There is no wiring from registry linking, from the spine, or from any job.

## 3. Overlap — do both tables get populated for a registry-linked page?

**No.** They are disjoint by construction:

```
Dashboard "link to registry"  ──HTTP──►  POST /api/registry/deliverables
                                              └─► deliverables            ✅
                                                  qa_bridge_map           ❌ never

LinkSpy admin UI (QaBridgePanel) ──────►  POST /api/sites/{id}/qa-bridge/maps
                                              └─► qa_bridge_map           ✅
                                                  deliverables            ❌ never
```

A row exists in both **only** if an operator happened to do both actions by hand
for the same page.

### 3.1 The consequence — this is a live functional gap, not just debt

Both tables key on **the Dashboard's `Page.id`**:

- `qa_bridge_map.qa_page_ref` ← `Page.id`
- `deliverables.external_ref` ← `Page.id` (`022_deliverables.sql:19` — *"the peer
  app's id for this thing (e.g. QA Page.id)"*)

The Dashboard's "Still True Today" module calls
`/api/qa-bridge/status?qa_page_ref={Page.id}` (`src/lib/linkspy/client.ts:31`),
which resolves through **R1 → `qa_bridge_map` only**.

So for a page that was linked through the registry — the modern, documented
path — the status endpoint returns `{"mapped": false}` and the Dashboard module
renders its quiet "not yet linked" state, **even though LinkSpy holds a perfectly
good `deliverables` row for that exact id.** The feature silently does nothing
unless someone also performs the legacy manual mapping.

This is the real defect. The "duplicative debt" framing had it backwards: the
problem is not that both tables are written, it is that **the reader only knows
about the older one.**

### 3.2 The field shapes are compatible

Which is what makes consolidation cheap and safe:

| `qa_bridge_map` | `deliverables` | Note |
|---|---|---|
| `qa_page_ref` | `external_ref` | both = Dashboard `Page.id`; both uniquely indexed |
| `linkspy_site_id` | `site_id` | both FK → `sites(id)` |
| `page_url` | `url` | both nullable |
| `created_at` | `created_at` | used as `baseline_at` for the snapshot |

Every field `qa_snapshot` needs is present in `deliverables`.

---

## 4. Strategy chosen — A (adapted)

**Strategy A**, with one deviation from the brief worth calling out.

The brief's Strategy A said *"stop writing to `qa_bridge_map` in new code paths"*.
There are no automatic writes to stop — W1/W2 are both deliberate operator
actions in an admin UI that is still shipped and still useful. Removing them
would be a feature regression, not a cleanup. **So the writers stay.**

What consolidates is the **read** path: R1 gains a registry fallback.

```
qa_resolve_map(qa_page_ref):
    row = qa_get_map(qa_page_ref)          # legacy table FIRST — always wins
    if row: return row                      # → byte-identical to today
    if QA_BRIDGE_CONSOLIDATION != "1": return None
    d = registry_get_deliverable(qa_page_ref)   # fallback: registry
    return adapt(d) if d else None
```

Why legacy-first rather than registry-first: an explicit manual mapping is a
deliberate operator override (the upsert comment at `database.py:2593` calls it
*"explicit re-link overwrites the prior source"*). It must keep winning, and
legacy-first also guarantees the flag can never change behaviour for any ref
that resolves today.

**Strategy B (SQL view) rejected.** It would require dropping the physical table
to put a view in its place — destructive DDL, forbidden by the Constitution, and
it would break W1/W2 (views are not upsertable without triggers). Strategy A
achieves the unification with zero DDL.

### What is explicitly NOT done
- No table dropped, no row deleted, no column removed.
- No migration in this change at all — **zero DDL**.
- `qa_bridge_map` keeps every existing row and both writers.
- Flag OFF ⇒ not one byte of behaviour changes.

---

## 5. Activation & rollback

Flag lives on **Railway** (the backend is the only reader).

- `QA_BRIDGE_CONSOLIDATION` unset / anything but `1` → today's behaviour exactly.
- `QA_BRIDGE_CONSOLIDATION=1` → registry-linked pages start resolving.

Note the truthiness idiom: strict `== "1"`, consistent with `JOBS_SHADOW` /
`FLYWHEEL` / `SPINE_CONSUME` (see INFRASTRUCTURE.md D8). `true`/`on` will **not**
work.

Rollback is deleting the variable and redeploying — no data to unwind, because
the flag only ever *adds* a fallback lookup that reads a table it never writes.

---

## 6. Follow-ups (not in this change)

- **30 days stable:** consider having the registry-link path also write a
  `qa_bridge_map` row for continuity, *or* formally deprecate `QaBridgePanel`'s
  manual mapping in favour of registry linking. Either is a separate decision.
- `qa_bridge_map` should **not** be dropped even then — R2/W1/W2 still serve the
  admin UI, and the rows are historical provenance (`created_by`, `created_at`).
- Consider surfacing "resolved via registry" vs "resolved via legacy map" in the
  status payload so the Dashboard can show provenance. Deliberately omitted here
  to keep the flag-off response byte-identical.
