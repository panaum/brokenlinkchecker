# P0 — Multi-tenancy foundation (Apexure Client Hub)

Pre-code plan. Nothing ships until this is approved. P0 is judged on its 403
tests and on the backfill leaving the current solo flow byte-identical.

## Diagnosis (what is actually true in the code today)

| Reality | Consequence |
|---|---|
| `GET /dashboard` returns **all sites, no `user_email` filter** | It's a **shared org**: every Apexure staffer sees every site — not per-user. |
| NextAuth `signIn` gates login to `@apexure.com` only | External **client_viewers can't log in** yet — the invite flow must extend `signIn`. |
| **No `users` table** (NextAuth = stateless JWT; users are email strings) | Memberships key on `user_email` (text); staff membership is **auto-provisioned on login**. |
| Backend routes take `site_id` / `scan_id` / `email` as **trusted params, no ownership check** | The entire authorization layer is **net-new**. |
| Backend is reachable **directly from the browser** (SSE → `NEXT_PUBLIC_BACKEND_URL`), and trusts the `email` query param | **The email param is spoofable.** Authorization MUST verify a signed identity, not read a query param. |
| `sites` + `scans` created manually; all other tables reference `sites(id)` via `site_id` | **`sites` is the single tenancy anchor**; child tables inherit scope through `site_id`. |

**This overturns the "one workspace per user_email" backfill.** Sites are not
partitioned per user today. Per-email workspaces would break the daily flow
(each staffer would see only sites they personally added). Correct,
behavior-preserving backfill: **one Apexure workspace, all staff as members,
all sites attached.**

## Identity verification (the load-bearing decision)

Because the backend is directly reachable and the `email` param is spoofable,
the backend must **authenticate** the caller before it can authorize:

- **Mechanism:** the frontend already holds a NextAuth JWT (signed with
  `NEXTAUTH_SECRET`). Forward it to the backend (Authorization header for fetch;
  `?token=` for the EventSource SSE calls, since EventSource can't set headers).
  The backend verifies the JWT signature with the shared secret and extracts a
  **trusted email**. No DB round-trip, stateless.
- Unverified/absent token → treated as anonymous → 401 on anything site-scoped
  (public capability routes below are exempt).
- This replaces "read the email from the session" everywhere in the auth layer.

## Backfill (make-or-break)

1. Create one workspace `Apexure` (owner = `anaum.pandit@apexure.com`).
2. `update sites set workspace_id = <apexure>` for every existing row (`client_id` null).
3. Staff memberships **auto-provisioned on login**: any verified `@apexure.com`
   caller with no membership gets a `member` row in the Apexure workspace
   (owner seeded for the primary email).
4. Result: every current user, next login, is a `member` seeing all workspace
   sites — **byte-identical to today**.

## Data model (migration, backwards-compatible, RLS in the same file)

```
workspaces  (id, name, owner_email, created_at)
clients     (id, workspace_id→workspaces, name, created_at)
memberships (id, user_email, workspace_id→workspaces, role, client_id→clients NULL, created_at,
             unique(user_email, workspace_id))         role ∈ {owner, member, client_viewer}
invites     (token PK, workspace_id, client_id NULL, email, role, created_at, expires_at,
             accepted_at NULL, revoked bool default false)
audit_log   (id, workspace_id, user_email, action, site_id NULL, at)
sites  ADD  workspace_id→workspaces NULL, client_id→clients NULL   -- nullable = applies pre-backfill
```
All new tables: `enable row level security` + a deny-by-default policy in the
same migration. `sites.workspace_id` nullable so the migration is safe to apply
before backfill; a later guard rejects null-workspace sites once backfilled.

## Authorization layer

`require_site_access(site_id, min_role)` FastAPI dependency, wrapped on every
site-scoped route:

```
1. verify JWT -> trusted caller email  (else 401)
2. load site.workspace_id / site.client_id
3. load caller membership in that workspace  (auto-provision @apexure.com as member)
4. rank: owner=3, member=2, client_viewer=1 ; role < min_role -> 403
5. client_viewer AND membership.client_id != site.client_id -> 403
6. allow
```
- URL-based routes (`/scan`, `/history`, `/uptime`) resolve `url → site → workspace`
  first. `/scan` on a new URL requires `member+` and stamps the site's `workspace_id`.
- `/dashboard` becomes scope-aware: `member+` → all workspace sites;
  `client_viewer` → only their `client_id` sites.

## Route inventory → min_role

| Route(s) | Type | min_role |
|---|---|---|
| `GET /dashboard` | read (scoped) | member / client_viewer |
| `GET /scan`, `/scan-site` | write | member |
| `POST /sites`, `DELETE /sites/{id}` | write | member |
| `GET /history`, `/uptime` | read | client_viewer |
| `GET /api/sites/{id}/diff/latest` | read | client_viewer |
| `GET /api/scans/{scan_id}/integrations` | read | client_viewer |
| SEO card/detail (PR 1) | read | client_viewer |
| `GET /api/findings/{id}/fix` · `/client-message` | remediation | member |
| `POST /api/findings/{id}/verify` | write | member |
| `GET /api/sites/{id}/fix-pack` · `/redirect-rules` | remediation | member |
| `*/monitoring` (get/set/run-now) · `/tracking-ids` | config/write | member |
| `*/forms/optin` (get/set) · `/forms/active-test` | dangerous | member |
| `POST /api/scans/{id}/share` · `DELETE /api/share/{token}` | write | member |
| `POST /api/self-heal/run` · `GET /status` | dangerous | member |
| SEO GSC CSV upload (PR 1) | write | member |
| `GET /api/watchdog/hosts` · `/api/diagnostics/*` · `POST /register` | agency/internal | member / owner |
| `GET /api/r/{token}` · `GET /api/sites/{id}/badge.svg` | public capability | public (unchanged) |
| `GET /preview` · `/api/xray` · `/api/prewarm` · `/health` | infra, url-based | public (pre-existing exposure) |

## NextAuth change
`signIn` allows if `@apexure.com` OR the email has an accepted membership OR a
valid (unexpired, unrevoked) invite. Sessions keep carrying `email`; the JWT is
what the backend verifies.

## Trust boundary (stated honestly)
Authorization is enforced in the **FastAPI layer** (single service-role Supabase
client) via `require_site_access` over a **verified JWT identity**. **RLS on the
new tables is deny-by-default defense-in-depth, NOT the primary boundary.** The
PR says this explicitly.

## Tests (the merge gate)
1. **Backfill snapshot:** `GET /dashboard` + a findings response byte-identical
   before/after migration for an `@apexure.com` member.
2. **Parameterized cross-scope 403:** a `client_viewer` scoped to client A hits
   every read route with a client-B `site_id`/`scan_id` → 403 on all.
3. **Viewer → write 403:** viewer hits every write route → 403.
4. **Spoof test:** request with a forged/absent JWT but a valid `email=` param → 401.
5. **Invite:** token single-use + expiring; revoke kills it.
6. **Nav-from-role:** viewer nav has no agency surface (asserted, not CSS-hidden).

## Resolved defaults
- Workspace owner email: **`anaum.pandit@apexure.com`**.
- `/preview` + `/api/xray`: **left public for P0** (pre-existing, orthogonal;
  rate-limiting is a separate follow-up).

## Build order within P0
1. Migration + RLS (this file's data model). ← safe, additive
2. JWT-verify util + `require_site_access` dependency + membership/workspace DB helpers.
3. Backfill (one Apexure workspace; attach sites; auto-provision on login).
4. Wrap every route per the inventory; make `/dashboard` scope-aware.
5. NextAuth `signIn` extension + forward JWT to backend.
6. Invites (create/accept/revoke) + audit_log.
7. Test suite (the six above).
