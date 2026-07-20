# INFRASTRUCTURE.md — Apexure QA ecosystem

The definitive map of every deployment surface, environment variable, shared
secret and feature flag across the three repos that make up the QA ecosystem.

**Everything here is derived from code**, by grepping every `process.env.*` /
`os.getenv(...)` / `os.environ[...]` reference in all three repositories and
reading the surrounding logic. Where the code disagrees with what we believed
was true, the code wins and the disagreement is recorded in
[Discrepancies found](#discrepancies-found).

**No real secret values appear in this file** — placeholders only.

| | |
|---|---|
| **Repos** | `panaum/brokenlinkchecker` (LinkSpy), `panaum/dashboard` (Deliverables Dashboard), `apexure-shell` (QA ecosystem shell) |
| **Surfaces** | 1 Railway service, 3 Vercel projects, 2 Supabase projects |
| **Last derived** | 2026-07-20 |
| **Mirrored at** | root of the LinkSpy repo **and** root of the Dashboard repo (keep both copies in sync) |

---

## Topology

```
                       ┌──────────────────────────────┐
                       │  Vercel: qa-ecosystem        │
                       │  (apexure-shell)             │
                       │  qa-ecosystem-2i6v.vercel.app│
                       └───────────┬──────────────────┘
                        /go/dashboard   /go/linkspy
                       (signed handoff token, TTL ≤300s)
                           │                   │
              ┌────────────▼─────┐   ┌─────────▼──────────────┐
              │ Vercel: dashboard│   │ Vercel:brokenlinkchecker│
              │ (Next.js 16)     │   │ (Next.js frontend)     │
              └────┬────────┬────┘   └────────┬───────────────┘
                   │        │                 │ every /api/* proxy
                   │        │                 │ (BACKEND_URL)
                   │        │                 ▼
                   │        │        ┌────────────────────────┐
                   │        └───────►│ Railway:               │
                   │   LINKSPY_API_  │ brokenlinkchecker      │
                   │   KEY (Bearer)  │ (FastAPI + Playwright) │
                   │                 └────────┬───────────────┘
                   │  spine events (HMAC)              │
                   │  ◄──────────────────────────────► │
                   ▼                                   ▼
        ┌────────────────────┐            ┌────────────────────┐
        │ Supabase: QA /     │            │ Supabase: LinkSpy  │
        │ Deliverables       │            │                    │
        └────────────────────┘            └────────────────────┘
```

---

## Discrepancies found

Ordered by operational severity. Each is a place where the code contradicts the
assumed state of the system.

### D1 — `DASHBOARD_BRIDGE_KEY` points at an endpoint that does not exist ⚠️

LinkSpy's frontend calls the Dashboard at
`{DASHBOARD_BRIDGE_URL}/api/registry-bridge/delivery?registry_site_id=…`
with `Authorization: Bearer {DASHBOARD_BRIDGE_KEY}`
(`frontend/app/api/delivery/route.ts:35-46`).

**The Dashboard has no `/api/registry-bridge/*` route.** Its complete API
surface is `/api/registry/clients`, `/api/registry/clients/[clientId]/sites`,
`/api/registry/prefills/refresh`, `/api/spine/drain`, `/api/spine/health`,
`/api/spine/inbox`, `/api/spine/outbox-status`. `DASHBOARD_BRIDGE_KEY` is read
nowhere in the Dashboard repo, and nowhere in the LinkSpy *backend* either.

Consequence: `/api/delivery` always falls into its catch and returns HTTP 200
`{ unavailable: true }` (or stale cache). It fails **silently and successfully**,
so nothing alerts. Either build the receiving route or delete the two vars.

### D2 — LinkSpy backend has no drain HTTP endpoint; there is no cron-job.org drain ⚠️

The expected "cron-job.org drain job" does not exist on the backend.
`spine_outbox_drain` is a **job-queue handler** (`backend/spine.py:86`), not a
route. It is enqueued internally by APScheduler every 5 minutes
(`backend/main.py:290-299`). Nothing in FastAPI is designed to be poked by an
external cron.

The only external-cron surfaces that actually exist are:
- **Dashboard** `/api/spine/drain` — cron-job.org, every 5 min. *(Until
  2026-07-20 this was a daily Vercel cron; that entry has been removed from
  `vercel.json` in favour of the external job.)*
- **LinkSpy frontend** `/api/cron/auto-scan` — but see D3.

### D3 — LinkSpy's cron route is almost certainly unreachable ⚠️

`frontend/middleware.ts:33`'s matcher excludes `login|handoff|portal|reports|
attest|api/auth|api/slack|api/portal|api/reports|api/attest|api/attestations|
_next/...`. **`api/cron` and `api/webhooks` are not in that exclusion list.**

So the auth middleware runs first, `getToken` returns null for a cookie-less
cron request, and it 307s to `/login` before the handler's `CRON_SECRET` check
ever executes. If an external cron is configured against this route today,
verify it is not simply collecting redirects. Same applies to the GitHub webhook.

### D4 — `PORTAL_ENFORCE` unset means the LinkSpy backend has no authorization at all ⚠️

`backend/auth.py:30` — when `PORTAL_ENFORCE` is falsy, every `require_*`
dependency returns `_BYPASS` (`auth.py:24,112`) = `role: "owner",
enforced: False`. Combined with the **service-role** Supabase key the backend is
built around (`auth.py:10-11`: *"authorization is enforced HERE… RLS is
deny-by-default defense-in-depth, not this"*), an unset `PORTAL_ENFORCE` means
unauthenticated cross-tenant read/write access to every tenant.

This is the single highest-stakes variable in the ecosystem. Confirm its value
on Railway.

### D5 — The shell's auth wall is disabled in committed code ⚠️

`apexure-shell/middleware.ts` is a pass-through (commit `abaf62d`, *"chore:
temporarily disable auth wall"*). The NextAuth config and the `@apexure.com`
domain gate in `lib/auth.ts:21-24` are intact but **inactive**. `/go/dashboard`
and `/go/linkspy` have no session check of their own, so anyone on the public
internet can mint a valid handoff token.

**Mitigation confirmed by reading both verifiers:** the token is friction-removal,
not auth. Dashboard's `/handoff` (`src/app/handoff/route.ts`) forwards only if
the browser already holds the `session` cookie, else redirects to `/login`.
LinkSpy's `/handoff` behaves the same against its NextAuth cookies. So a stolen
token grants nothing — but the shell's homepage copy *"Pick a door — you're
already signed in"* and its README are now false for anonymous visitors.

### D6 — `JOBS_MONITORING_LIVE=1` breaks monitoring rather than enabling it

`backend/jobs.py:144-155`: when the flag is `"1"`, `_monitoring_scan` skips the
shadow branch and immediately hits
`raise RuntimeError("monitoring_scan live path is not enabled yet (shadow only)")`.
Turning this on makes every `monitoring_scan` job **fail**. It must stay unset.

### D7 — `SPINE_SECRET` without `JOBS_SHADOW=1` silently queues work forever

The spine enqueue block is gated on `if os.getenv("SPINE_SECRET"):`
(`main.py:278`), but the worker that *executes* those jobs only starts under
`JOBS_SHADOW == "1"` (`main.py:262`). Set the secret without the flag and drain,
heartbeat and reconcile jobs accumulate in the `jobs` table and never run — with
no error anywhere.

### D8 — Two incompatible truthiness idioms for flags

- **Strict `== "1"`** — `JOBS_SHADOW`, `JOBS_MONITORING_LIVE`, `FLYWHEEL`,
  `SPINE_CONSUME`, `AUTO_ENROLL`, and the Dashboard's `SPINE_EMIT`.
- **Lenient `in ("1","true","yes","on")`** — `PORTAL_ENFORCE` (`auth.py:30`),
  `TRACER_ENABLED`, `ACTIVE_FORM_TESTING`, `SELF_HEAL`.

`PORTAL_ENFORCE=on` works; `FLYWHEEL=on` silently does nothing. Always use `1`.

### D9 — `DIRECT_URL` is the pooler in session mode, not the direct host

`docs/runbooks/backup.md:21-23,58-60` describes dumping against "the DIRECT
connection… not the pooled one", implying `db.<ref>.supabase.co`. In reality
**both** Dashboard URLs use the pooler host, differing only by port:

| Var | Host | Port | Mode |
|---|---|---|---|
| `DATABASE_URL` | `aws-1-ap-southeast-2.pooler.supabase.com` | 6543 | transaction (pgbouncer) |
| `DIRECT_URL` | `aws-1-ap-southeast-2.pooler.supabase.com` | 5432 | **session** |

This is correct and necessary — the true direct host is IPv6-only, and the
pooler is the IPv4 path. The functional advice (use 5432, never 6543) still
holds; the *wording* in the runbook is misleading. Region `ap-southeast-2`
(Sydney) matches `vercel.json`'s `syd1` pin.

### D10 — Dead variables

| Var | Surface | Why dead |
|---|---|---|
| `AUTH_SECRET` | Vercel brokenlinkchecker | NextAuth **v5** name; that app is v4 and reads `NEXTAUTH_SECRET`. Inert if set. |
| `AUTH_TRUST_HOST` | Vercel brokenlinkchecker | v5-only. Never read. |
| `PORT` | Railway | Consumed by the shell in `Dockerfile:7` (`--port $PORT`), never by Python. It is also the *only* var `README.md:58` documents for the backend. |
| `BOARD_URL` | Vercel qa-ecosystem | Not dead — deliberate forward-looking placeholder for the third door (`README.md:51-54`). Setting it today has no effect. |

### D11 — Documentation gaps

- **Dashboard `.env.example` omits three vars its code reads**: `SPINE_SECRET`,
  `SPINE_EMIT`, `CRON_SECRET`.
- **LinkSpy backend `README.md` documents only `PORT`** — the one var Python
  never reads. All 21 backend vars are otherwise undocumented as deployment config.
- **LinkSpy frontend has no `.env.example` and no `vercel.json`** — all 12 of its
  vars are undocumented in-repo.
- `src/lib/handoff-contract.ts`'s header comment in the **Dashboard** repo claims
  *"LinkSpy: frontend/lib/handoff-contract.ts (this file)"* — copy-paste artifact
  from the mirrored file.

### D12 — Inconsistent constant-time comparison

`handoff-contract.ts` and `spine-contract` (both languages) use
`timingSafeEqual` / `hmac.compare_digest`. But
`frontend/app/api/webhooks/github/route.ts:20` and
`frontend/app/api/cron/auto-scan/route.ts:9` use plain `!==` string compares.
Minor, but inconsistent with the rest of the codebase.

### D13 — Endpoints that fail open

| Endpoint | Behaviour when its secret is unset |
|---|---|
| Dashboard `/api/spine/drain` | `authorized()` returns `true` — *"not yet configured → allow (pre-activation)"* |
| Dashboard `/api/spine/outbox-status` | Auth check is `if (secret && …)` — unset ⇒ open |
| LinkSpy `/api/cron/auto-scan` | Guard is `if (cronSecret && …)` — unset ⇒ public scan trigger |
| LinkSpy backend (all routes) | `PORTAL_ENFORCE` unset ⇒ `_BYPASS` (see D4) |

Dashboard `/api/spine/health` has **no auth at all** by design, and exposes
`SPINE_EMIT` state plus outbox counts.

---

## 1. Per-surface variable tables

**Type** legend: `secret` (credential — rotate), `url` (endpoint), `flag`
(on/off), `tuning` (numeric), `platform` (injected by the host).

### 1.1 Railway — `brokenlinkchecker` service (LinkSpy backend)

FastAPI + Playwright/Chromium, `Dockerfile` at repo root, `CMD uvicorn main:app
--host 0.0.0.0 --port $PORT`. No `railway.json`/`nixpacks.toml`/`Procfile` in the
repo — Railway config is dashboard-managed, so the live variable set cannot be
verified from source. There is no pydantic `Settings` class; every read is a bare
`os.getenv`. `load_dotenv()` runs once at `database.py:7`.

| Variable | Purpose | Type | Shared with | Currently required |
|---|---|---|---|---|
| `SUPABASE_URL` | LinkSpy Supabase project URL for `create_client` (`database.py:9,15`) | url | — | **Yes** — `_get_client()` raises → 500 on every DB route |
| `SUPABASE_KEY` | Supabase **service-role** key; backend is the trust boundary (`auth.py:10-11`) | secret | — | **Yes** — same raise (misleadingly says `"supabase_url is required"`) |
| `PORTAL_ENFORCE` | Master authorization switch for all `require_*` deps (`auth.py:30`) | flag | — | **Effectively yes** — see D4 |
| `BACKEND_AUTH_SECRET` | HS256 key verifying portal tokens minted by the LinkSpy frontend (`auth.py:35`); Fernet key material (`tracer_crypto.py:23`) | secret | Vercel brokenlinkchecker | Only when `PORTAL_ENFORCE` is on |
| `NEXTAUTH_SECRET` | Fallback for the above — precedence `BACKEND_AUTH_SECRET or NEXTAUTH_SECRET or ""`, identical on both sides | secret | Vercel brokenlinkchecker | Fallback only |
| `SPINE_SECRET` | HMAC-SHA256 key for the spine bus, both directions (`main.py:3403`, `spine.py:98`) | secret | **Vercel dashboard, Vercel qa-ecosystem, Vercel brokenlinkchecker** | Yes for spine — inbox 503s without it |
| `QA_APP_URL` | Dashboard base for outbox POST + reconcile GET (`spine.py:97,166`) | url | — | Yes for spine — drain returns `{"skipped":"not configured"}` |
| `SPINE_CONSUME` | Whether inbound `deliverable.ready_for_qa` enqueues a `qa_battery` job (`main.py:3435`) | flag | — | No — off = record-only shadow |
| `FLYWHEEL` | Gap-analysis / candidate-drafting loop (`flywheel.py:88`) | flag | — | No — off = no-op |
| `AUTO_ENROLL` | Auto-enrol a site into weekly monitoring on `qa.completed` (`spine.py:47`) | flag | — | No |
| `JOBS_SHADOW` | Starts the asyncio jobs worker + 30-min shadow enqueue (`jobs.py:162`, `main.py:262`) | flag | — | **Effectively yes** — without it nothing drains (D7) |
| `JOBS_MONITORING_LIVE` | Whether `monitoring_scan` does real work (`jobs.py:144`) | flag | — | **Must stay unset** (D6) |
| `JOBS_LEASE_SECONDS` | `p_lease_seconds` for the `jobs_claim` RPC (`jobs.py:19`) | tuning | — | No — default `"60"` |
| `JOBS_POLL_SECONDS` | Sleep between empty claim polls (`jobs.py:20`) | tuning | — | No — default `"2"` |
| `SLACK_WEBHOOK_URL` | Incoming-webhook for all 5 notifiers (`main.py:97,342,2260,3057`, `spine.py:15`) | secret | — | No — every site does `if not webhook: return` |
| `FRONTEND_URL` | Base for report/share/invite links (`main.py:21`, `spine.py:56`) | url | — | No — `main.py` falls back to a hardcoded Vercel URL |
| `TRACER_CRYPTO_KEY` | Explicit Fernet key for CRM credential encryption at rest (`tracer_crypto.py:20`) | secret | — | No — falls back to the auth secrets; `RuntimeError` if all three unset |
| `TRACER_ENABLED` | Arms the daily lead-tracer sweep (`tracer.py:26`) | flag | — | No |
| `ACTIVE_FORM_TESTING` | Global switch for active (submitting) form tests (`active_submission.py:39`) | flag | — | No |
| `SELF_HEAL` | Master switch for the self-heal PR opener (`self_heal.py:44`) | flag | — | Yes for that route — 403 `"SELF_HEAL is off."` |
| `SELF_HEAL_ALLOWLIST` | Comma/space list of `owner/repo` allowed to receive PRs (`self_heal.py:51`) | — | — | Yes for that route — empty ⇒ every repo 403 |
| `SELF_HEAL_GITHUB_TOKEN` | GitHub token for opening fix PRs (`main.py:1732`) | secret | — | Yes for that route — 400 `refused: true` |
| `PORT` | Injected by Railway; used by `Dockerfile` shell only | platform | — | **Dead in Python** (D10) |

### 1.2 Vercel — `brokenlinkchecker` project (LinkSpy frontend)

Next.js, NextAuth **v4** (`next-auth@4.24.14`). No `vercel.json`, no
`.env.example` — every var below is undocumented in-repo.

| Variable | Purpose | Type | Shared with | Currently required |
|---|---|---|---|---|
| `BACKEND_URL` | Server-side origin for every Next→Railway proxy fetch (~90 route files) | url | — | **Yes** — defaults to `http://localhost:8000`; silently fails on Vercel |
| `NEXT_PUBLIC_BACKEND_URL` | Client-side SSE origin, bypassing Vercel's function timeout for long scans (`app/page.tsx:208`) | url | — | No — falls back to the same-origin proxy, but long scans then time out |
| `NEXTAUTH_SECRET` | JWT decryption for the middleware auth wall (`middleware.ts:7`); fallback backend-token key | secret | Railway | **Yes** — `getToken` null ⇒ every request redirects to `/login` |
| `NEXTAUTH_URL` | Canonical callback base; read by NextAuth internals, not app code | url | — | Optional on Vercel (derived from `VERCEL_URL`); needed for a custom domain |
| `BACKEND_AUTH_SECRET` | Primary HS256 key minting the backend token (`lib/backendToken.ts:10`) | secret | Railway | No — degrades to anonymous backend calls |
| `GOOGLE_CLIENT_ID` | Google OAuth client (`app/api/auth/[...nextauth]/route.ts:9`) | secret | — | **Yes** — non-null asserted; OAuth errors without it |
| `GOOGLE_CLIENT_SECRET` | Google OAuth token exchange (`:10`) | secret | — | **Yes** — fails at callback |
| `SPINE_SECRET` | HMAC key for handoff tokens (`api/handoff/sign/route.ts:9`, `handoff/route.ts:17`, `api/delivery/route.ts:21`) | secret | **Railway, Vercel dashboard, Vercel qa-ecosystem** | Yes for handoff — sign 503s |
| `DASHBOARD_APP_URL` | Base origin handoff links point at (`api/handoff/sign/route.ts:15`) | url | — | Yes for handoff — 400 `"no target base"` |
| `DASHBOARD_BRIDGE_URL` | Dashboard read-API origin for delivery data (`api/delivery/route.ts:35`) | url | — | **No — target route does not exist (D1)** |
| `DASHBOARD_BRIDGE_KEY` | Bearer credential for that bridge (`:36`) | secret | *(nominally Vercel dashboard)* | **No — never validated anywhere (D1)** |
| `CRON_SECRET` | Bearer auth on `/api/cron/auto-scan` (`:7`) | secret | Vercel dashboard *(separate endpoint)* | Fails open if unset; route likely unreachable (D3) |
| `GITHUB_WEBHOOK_SECRET` | HMAC verification of GitHub deployment webhooks (`api/webhooks/github/route.ts:6`) | secret | GitHub repo settings | Yes for that route — 401 otherwise |
| `AUTH_SECRET` | — | — | — | **Dead** — v5 name (D10) |
| `AUTH_TRUST_HOST` | — | — | — | **Dead** — v5 name (D10) |

### 1.3 Vercel — `dashboard` project (Deliverables Dashboard)

Next.js 16 + Prisma 6. `vercel.json` pins `regions: ["syd1"]` and one cron.
Auth is a shared team password + signed cookie — **not** NextAuth.

| Variable | Purpose | Type | Shared with | Currently required |
|---|---|---|---|---|
| `DATABASE_URL` | Supabase **pooled** connection, port 6543/pgbouncer (`schema.prisma`) | secret | — | **Yes** |
| `DIRECT_URL` | Supabase **session** connection, port 5432 — migrations + bulk import (`schema.prisma`, `prisma/import-2026.ts:8`) | secret | — | **Yes** |
| `APP_PASSWORD` | Shared team password, timing-safe compared (`lib/auth.ts:35`) | secret | — | **Yes** — empty ⇒ nobody can log in |
| `AUTH_SECRET` | HMAC key signing the `session` cookie (`lib/auth.ts:10`) | secret | — | **Yes** — falls back to the literal `"dev-secret"` |
| `SPINE_SECRET` | HMAC for spine inbox + drain, Bearer for outbox-status, handoff verification (`api/spine/inbox/route.ts:11`, `drain:37`, `outbox-status:7`, `handoff/route.ts:16`) | secret | **Railway, Vercel qa-ecosystem, Vercel brokenlinkchecker** | Yes for spine — inbox 503s, handoff redirects home |
| `SPINE_EMIT` | Gates whether outbox rows are ever written (`lib/spine-emit.ts:9`) | flag | — | No — unset ⇒ status actions behave identically to pre-spine |
| `CRON_SECRET` | Bearer auth on `/api/spine/drain` (`drain:21`) | secret | Vercel brokenlinkchecker *(separate endpoint)*, Vercel cron | **Fails open if unset** (D13) |
| `LINKSPY_API_URL` | LinkSpy backend base for the registry + QA-bridge clients (`lib/registry.ts:11`, `lib/linkspy/client.ts:18`, `drain:36`) | url | — | No — feature silently unavailable |
| `LINKSPY_API_KEY` | Bearer service key for those calls; **server-only, never reaches the browser** | secret | LinkSpy (validated backend-side) | No — `registryConfigured()` false ⇒ typed "unavailable" |
| `LINKSPY_APP_URL` | LinkSpy dashboard base for operator deep links (`lib/linkspy/client.ts:24`) | url | — | No — falls back to `LINKSPY_API_URL`, then plain instructions |
| `ANTHROPIC_API_KEY` | Enables Claude judgment in the AI QA agent (`lib/ai/anthropic.ts:5`) | secret | — | No — deterministic checks still run |
| `E2E_PASSWORD` | Playwright login; must equal the server's `APP_PASSWORD` (`e2e/auth.setup.ts:15`) | secret | — | Test-only |
| `NODE_ENV` | Cookie `secure` flag, Prisma client caching | platform | — | Injected |

### 1.4 Vercel — `qa-ecosystem` project (apexure-shell)

Deployed at `qa-ecosystem-2i6v.vercel.app`. Small — 11 source files, no
`vercel.json`. NextAuth v4 with a Google Workspace domain gate.

| Variable | Purpose | Type | Shared with | Currently required |
|---|---|---|---|---|
| `SPINE_SECRET` | HMAC-SHA256 key signing handoff tokens for both doors (`app/go/[app]/route.ts:14`) | secret | **Railway, Vercel dashboard, Vercel brokenlinkchecker** | **Yes** — unset ⇒ both doors silently 302 to `/` |
| `DASHBOARD_URL` | Base URL of the Dashboard app (`route.ts:8`) | url | — | **Yes** for the dashboard door |
| `LINKSPY_URL` | Base URL of LinkSpy (`route.ts:9`) | url | — | **Yes** for the linkspy door |
| `GOOGLE_CLIENT_ID` | Google OAuth client (`lib/auth.ts:11`) | secret | — | Yes **if auth is re-enabled** (D5) |
| `GOOGLE_CLIENT_SECRET` | Google OAuth secret (`lib/auth.ts:12`) | secret | — | Yes **if auth is re-enabled** |
| `NEXTAUTH_SECRET` | JWT signing; read by NextAuth internals, not app code | secret | — | **Yes in production** — v4 throws `NO_SECRET` without it |
| `NEXTAUTH_URL` | Callback base; derived from `VERCEL_URL` on Vercel | url | — | Optional |
| `BOARD_URL` | Third door, not yet wired | url | — | **No** — never read (D10) |

Door registry (`app/go/[app]/route.ts:7-10`, evaluated at module load):

| Slug | Target | State |
|---|---|---|
| `dashboard` | `DASHBOARD_URL` → `{base}/handoff?token=…` | live |
| `linkspy` | `LINKSPY_URL` → `{base}/handoff?token=…` | live |
| `board` | absent from `DEST` | 302 to `/`; UI card is inert (`disabled`, badge "Soon") |

---

## 2. Shared-secret map

### `SPINE_SECRET` — 4 surfaces

The most widely shared value in the ecosystem. Must be **byte-identical** on
Railway, Vercel `dashboard`, Vercel `qa-ecosystem`, and Vercel
`brokenlinkchecker`. (The original brief listed three surfaces — the LinkSpy
frontend is the fourth, and it needs the value for handoff signing.)

It carries **three different auth mechanisms**, which is worth knowing when
rotating:

1. **Spine envelope HMAC** — `HMAC-SHA256(secret, rawBody)` → lowercase hex,
   sent as `x-spine-signature` with `x-spine-sent-at` (unix seconds).
   `SKEW_MAX_SECONDS = 300`. Verified with `timingSafeEqual` /
   `hmac.compare_digest`. Contract duplicated verbatim in
   `backend/spine_contract.py` and `src/lib/spine-contract.ts`, guarded by
   `CONTRACT_CHECKSUM = 36924adb…`.
2. **Handoff token** — `base64url({target_path, exp, nonce}) + "." + hex HMAC`.
   `HANDOFF_MAX_TTL_S = 300`, hard-capped. Guarded by
   `HANDOFF_CHECKSUM = 90b6a00d…` — **verified identical in the shell and
   Dashboard copies**.
3. **Plain bearer** — LinkSpy's reconcile (`spine.py:178`) uses the same secret
   as `Authorization: Bearer …` against the Dashboard's `/api/spine/outbox-status`.
   A weaker mode on the same key; noted, not currently a defect.

### `DASHBOARD_BRIDGE_KEY` — 1 surface, orphaned

Set on Vercel `brokenlinkchecker` only. Read at
`frontend/app/api/delivery/route.ts:36`. **Validated by nothing** — see D1.

### `LINKSPY_API_KEY` — 1 surface + backend validation

Set on Vercel `dashboard`; sent as `Authorization: Bearer …` to
`{LINKSPY_API_URL}/api/registry/*` and `/api/qa-bridge/*`. Read server-side only
(`src/lib/registry.ts`, `src/lib/linkspy/client.ts` — both `import "server-only"`),
so it never reaches the browser. Not read by the LinkSpy *frontend*; the LinkSpy
*backend* is what authorizes it.

### `BACKEND_AUTH_SECRET` / `NEXTAUTH_SECRET` — Railway + Vercel brokenlinkchecker

Precedence is identical on both sides — `BACKEND_AUTH_SECRET or NEXTAUTH_SECRET
or ""` (`lib/backendToken.ts:10`, `backend/auth.py:35`). Mints a hand-rolled
HS256 JWT `{email, iat, exp}`, default TTL 3600s frontend-side, 30 days for
portal tokens backend-side.

### `CRON_SECRET` — 2 surfaces, 2 unrelated endpoints

Not one shared secret in practice. Vercel `dashboard` uses it for
`/api/spine/drain`; Vercel `brokenlinkchecker` uses it for `/api/cron/auto-scan`.
They may hold different values. **Both fail open when unset.**

### Missing / dead summary

| Secret | Referenced in code at | Missing from | Note |
|---|---|---|---|
| `DASHBOARD_BRIDGE_KEY` | LinkSpy frontend | Dashboard (no consumer route) | D1 |
| `SPINE_SECRET` | 4 surfaces | Dashboard `.env.example` | D11 |
| `SPINE_EMIT` | Dashboard | Dashboard `.env.example` | D11 |
| `CRON_SECRET` | Dashboard, LinkSpy frontend | Dashboard `.env.example` | D11 |
| `AUTH_SECRET`, `AUTH_TRUST_HOST` | nowhere (v5 names) | — | Dead if set on Vercel brokenlinkchecker |
| `PORT` | `Dockerfile` only | — | Dead in Python |

---

## 3. Flags registry

All flags below are **off/unset by default**. Remember D8: the spine/jobs flags
accept **only the literal string `1`**.

| Flag | Surface | Test | ON | OFF / unset |
|---|---|---|---|---|
| `JOBS_SHADOW=1` | Railway | `== "1"` | Starts the asyncio jobs worker at boot + a 30-min `shadow_enqueue_monitoring` APScheduler job | **No worker exists at all** — the queue is never drained (D7) |
| `SPINE_EMIT=1` | Vercel dashboard | `=== "1"` | Status/cert transitions write `SpineOutbox` rows inside the same transaction | No row is ever written; status actions behave byte-identically to pre-spine |
| `SPINE_CONSUME=1` | Railway | `== "1"` | Inbound `deliverable.ready_for_qa` enqueues a `qa_battery` job | Event still lands in `spine_inbox` + timeline, but `enqueued: false` — record-only shadow |
| `AUTO_ENROLL=1` | Railway | `== "1"` | On `qa.completed`, enrols an unmonitored site into Weekly monitoring + timeline + Slack | `{"enrolled": false}`. Already-monitored sites are skipped either way, so cadence is never downgraded |
| `FLYWHEEL=1` | Railway | `!= "1"` → skip | `on_incident_resolved` classifies the incident and may draft a checklist candidate + enqueue a spine event | Returns `{"skipped": true}` before any DB import — pure no-op |
| `JOBS_MONITORING_LIVE` | Railway | `== "1"` | **`RuntimeError` — the live path is deliberately unimplemented (D6)** | Correct state. Prints `[jobs:shadow] would scan site=… — dry-run` |

Sequencing note: the flywheel only produces visible effect with
`JOBS_SHADOW=1` **and** `SPINE_SECRET` set on Railway, plus `SPINE_EMIT=1` on the
Dashboard for the reverse direction.

---

## 4. External services

### Supabase — two separate projects, both FREE TIER

| Project | Consumed by | Connection |
|---|---|---|
| **QA / Deliverables** | Dashboard (Prisma) | `DATABASE_URL` (6543, pooled) + `DIRECT_URL` (5432, session) |
| **LinkSpy** | LinkSpy backend (`supabase-py`) | `SUPABASE_URL` + `SUPABASE_KEY` (service role) |

**Free tier ⇒ no PITR, no automatic downloadable backups.** The dump you take by
hand is the only copy that exists. Constitution rule 3: *no dump, no migration.*

**Connection string shape** (placeholders — never commit real values):

```
# pooled / transaction — app runtime, pgbouncer
postgresql://postgres.<PROJECT_REF>:<PASSWORD>@aws-1-ap-southeast-2.pooler.supabase.com:6543/postgres?pgbouncer=true

# session — migrations, bulk import, AND pg_dump
postgresql://postgres.<PROJECT_REF>:<PASSWORD>@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres
```

Use the **pooler host in session mode (5432)** for `pg_dump` — the true direct
host (`db.<PROJECT_REF>.supabase.co`) is IPv6-only. Never dump against 6543:
pgbouncer in transaction mode breaks `pg_dump`. See D9.

**`pg_dump` requires PostgreSQL 17 client** — the server is PG17 and the client
major must be ≥ the server. On Windows: `C:\Program Files\PostgreSQL\17\bin`.
A v16 client aborts with *"server version mismatch"*.

### `C:\backups`

All dumps land in **`C:\backups`** — deliberately **outside OneDrive**, which has
previously locked and corrupted files in the working tree. Dumps are
secrets-adjacent (they contain all data): never commit them; `*.dump` / `*.sql`
belong in `.gitignore`.

Baseline of record (Gate −1, 2026-07-15):
`C:\backups\qa-dashboard-20260715-224052.dump` — 424,516 bytes, `pg_restore
--list` exit 0, all app tables present.

### Cron

| Job | Where | Schedule | Auth |
|---|---|---|---|
| Spine outbox drain | **cron-job.org** → Dashboard `/api/spine/drain` | every 5 min | `Authorization: Bearer {CRON_SECRET}` |
| Spine outbox drain | **Internal APScheduler** → LinkSpy job queue | every 5 min | none (in-process) |
| Auto-scan | LinkSpy frontend `/api/cron/auto-scan` | external (cron-job.org) | `Authorization: Bearer {CRON_SECRET}`, **POST only** |

**The Vercel cron was removed** (2026-07-20). `vercel.json` previously carried
`{ "path": "/api/spine/drain", "schedule": "0 3 * * *" }`, but Vercel **Hobby**
only permits daily crons, which was too slow to be useful. The external
cron-job.org job at a 5-minute cadence supersedes it. `vercel.json` still exists
— it pins `regions: ["syd1"]` to co-locate functions with the Sydney Supabase
project, which must not be removed.

Consequence to be aware of: **the automated drain now depends entirely on an
external service.** If the cron-job.org job is paused or its bearer drifts,
nothing on Vercel will pick up the slack — the queue simply grows. Watch the
*"spine heartbeat silent >2h"* Slack alert as the signal. For immediate
delivery, drain manually (see runbook 5.4) — the route is idempotent and unrated.

If cron-job.org is used against `/api/cron/auto-scan`, note it must issue **POST**
(there is no `GET` export → 405) and that middleware likely intercepts it (D3).

### Slack

One incoming webhook (`SLACK_WEBHOOK_URL`, Railway only), five emitters:

| Emitter | Fires on |
|---|---|
| `send_slack_notification` | Completed scan results |
| `_watchdog_slack` | Third-party outage / sentinel / uptime / lead-tracer alerts |
| `_report_slack` | Vigilance report ready — links to `{FRONTEND_URL}/reports/{id}` |
| `_consent_drift_alert` | Consent observation drift (silent on first run) |
| `spine._slack` | Auto-enrol confirmation; spine heartbeat silent >2h; reconcile drift; flywheel probe needed |

All best-effort — exceptions are swallowed (`spine.py:21`, `main.py:2269`).

---

## 5. Runbooks

### 5.1 Adding an environment variable

**Railway (`brokenlinkchecker`)**
1. Service → **Variables** → **New Variable**.
2. **Railway does not auto-restart on variable change** — click **Deploy** (or
   Deployments → Redeploy) explicitly. The value is not live until you do.
3. Verify: `GET /api/spine/health`-equivalent, or check startup logs for the
   flag echo at `main.py:3317-3318`.

**Vercel (any of the three projects)**
1. Project → **Settings → Environment Variables** → add for **Production**
   (and Preview/Development if needed).
2. **Existing deployments do not pick it up** — trigger a redeploy:
   Deployments → ⋯ → **Redeploy**, or push an empty commit.
3. `NEXT_PUBLIC_*` vars are **inlined at build time** — a redeploy is mandatory,
   not optional.
4. Verify: Dashboard → `GET /api/spine/health` returns `{ emit: true|false, … }`.

### 5.2 Rotating a secret

Order matters — rotate the consumer last where a mismatch would drop traffic.

**`SPINE_SECRET`** (4 surfaces; HMAC has ±300s skew but **no key rotation
grace** — a mismatch is a hard 401)
1. Generate: `openssl rand -hex 32`.
2. Drain first: `POST /api/spine/drain` on the Dashboard until
   `{ remaining: 0 }`, so no signed-in-flight events are stranded.
3. Update **all four** surfaces: Railway, Vercel `dashboard`, Vercel
   `qa-ecosystem`, Vercel `brokenlinkchecker`.
4. Redeploy all four (Railway needs explicit Deploy).
5. Verify: shell `/go/dashboard` completes the handoff; Dashboard
   `/api/spine/health` shows deliveries resuming; watch for the
   *"spine heartbeat silent >2h"* Slack alert as the failure signal.

**`DASHBOARD_BRIDGE_KEY`** — currently inert (D1). Rotate freely, or delete it
and `DASHBOARD_BRIDGE_URL` together once the decision on the bridge is made.

**`LINKSPY_API_KEY`**
1. Mint in LinkSpy: Site → Settings → QA Dashboard link.
2. Set on Vercel `dashboard`, redeploy.
3. Verify: the "Still True Today" module on a page detail renders live status
   instead of its quiet "not yet linked" state. Failure is silent by design
   (`registryConfigured()` false ⇒ typed "unavailable"), so check the UI, not logs.

**`CRON_SECRET`** — remember these are two independent values.
- Dashboard: set → redeploy → confirm the Vercel cron run at 03:00 UTC returns
  200, or drain manually with the new bearer.
- LinkSpy frontend: set → redeploy → update the cron-job.org job header.
- **Never leave unset** — both endpoints fail open (D13).

**`APP_PASSWORD` / `AUTH_SECRET` (Dashboard)** — rotating `AUTH_SECRET`
invalidates every existing `session` cookie (30-day maxAge), logging the whole
team out. Expected, but announce it. Keep `E2E_PASSWORD` equal to
`APP_PASSWORD` or Playwright's `auth.setup.ts` will fail.

**`SUPABASE_KEY`** — service role. Rotate in Supabase → Settings → API, then
Railway → Deploy. Every DB route 500s in the gap, so do it in a quiet window.

### 5.3 Taking a dump (do this before ANY migration)

```bash
export PGSSLMODE=require                 # Supabase requires SSL
STAMP="$(date +%Y%m%d-%H%M%S)"

# QA / Deliverables — session mode (5432), pooler host
pg_dump "$DIRECT_URL" --no-owner --no-privileges --format=custom \
  --file="C:/backups/qa-dashboard-${STAMP}.dump"

# Verify it is real before trusting it
pg_restore --list "C:/backups/qa-dashboard-${STAMP}.dump" | head -40
ls -l "C:/backups/qa-dashboard-${STAMP}.dump"
```

```bash
# LinkSpy
pg_dump "$LINKSPY_DIRECT_URL" --no-owner --no-privileges --format=custom \
  --file="C:/backups/linkspy-${STAMP}.dump"
pg_restore --list "C:/backups/linkspy-${STAMP}.dump" | head -40
```

Then record the filename in the migration PR. Checklist:

```
- [ ] Dump taken against the target project
- [ ] Dump filename: __________________________
- [ ] Verified: size = _____ , pg_restore --list shows expected tables
- [ ] Stored in C:\backups (outside OneDrive)
- [ ] Migration is additive-only (no DROP / rename / type-narrowing)
```

Full detail, restore procedure and the free-tier rationale live in
`docs/runbooks/backup.md` (mirrored in both repos).

### 5.4 Manual drain

The daily Vercel cron is often too slow while testing. The route is idempotent
and has no rate limit — call it as often as you like.

```bash
curl -X POST -H "Authorization: Bearer $CRON_SECRET" \
  https://<dashboard-host>/api/spine/drain
# → {"delivered":N,"failed":N,"remaining":N,"heartbeat_emitted":bool}
```

Both `GET` and `POST` are accepted. Repeat until `remaining: 0`.

Diagnosing a drain that does nothing:

| Symptom | Cause |
|---|---|
| `{"skipped":"spine not configured"}` | `LINKSPY_API_URL` or `SPINE_SECRET` unset on the Dashboard |
| `401 unauthorized` | `CRON_SECRET` mismatch |
| `failed > 0`, rows retry forever | Check `SpineOutbox.lastError`; usually a 401 from LinkSpy ⇒ `SPINE_SECRET` drift, or `>300s` clock skew |
| Nothing ever enqueued | `SPINE_EMIT` is not `1` on the Dashboard |
| LinkSpy side never drains | `JOBS_SHADOW` is not `1` on Railway — no worker exists (D7) |

Health check (unauthenticated, safe to curl):

```bash
curl https://<dashboard-host>/api/spine/health
# → {"emit":bool,"undelivered":N,"last_delivered_at":"…"}
```

---

## Manual cleanup required

Dashboard-console changes an operator must make by hand — environment variables
cannot be removed from a repo, and the Vercel/Railway CLIs are not wired up here.

### Vercel `brokenlinkchecker` project — remove two dead variables

`AUTH_SECRET` and `AUTH_TRUST_HOST` are **NextAuth v5** names. That app runs
NextAuth **v4** (`next-auth@4.24.14`), which reads `NEXTAUTH_SECRET`. Both are
inert: setting them does nothing, and their presence misleads anyone reading the
env list into thinking they are the live auth secrets. See D10.

For each of `AUTH_SECRET`, then `AUTH_TRUST_HOST`:

1. Vercel dashboard → **brokenlinkchecker** project → **Settings** →
   **Environment Variables**.
2. Find the variable in the list.
3. Three-dot menu (⋯) at the right of its row → **Remove** → confirm.
4. After removing both: **Deployments** → latest production deployment →
   ⋯ → **Redeploy**.
5. Verify sign-in still works — `NEXTAUTH_SECRET` is the one that matters, and
   it must remain set. If sign-in breaks, you removed the wrong variable.

> Do these two together and redeploy once. Removing an env var does **not** take
> effect until a redeploy.

### Not to be removed — checked and live

Recorded here because it has been proposed for removal on the mistaken belief
that it is unused:

| Variable | Surface | Status |
|---|---|---|
| `LINKSPY_APP_URL` | Vercel `dashboard` | **LIVE — do not remove.** Read at `src/lib/linkspy/client.ts:24` (`linkspyAppUrl()`) and `src/app/dashboard/checklists/candidates/page.tsx:27`. Removing it makes operator deep links fall back to `LINKSPY_API_URL` — the *backend* base, not a URL a human should land on — and strips the LinkSpy links from the checklist-candidates page entirely. |
| `AGENCY_APP_URL` | — | **Does not exist.** Zero references in any of the three repos. If you see it set on a Vercel project, it is genuinely dead and safe to remove, but it is not part of this system. |

`BOARD_URL` on Vercel `qa-ecosystem` is also unread, but leave it — it is
deliberate scaffolding for the third door (D10).

---

## Maintaining this file

Two identical copies exist, at the root of the LinkSpy repo and the Dashboard
repo. When either changes, update both in the same session — there is no
automation keeping them in sync.

Re-derive after any change to deployment config by grepping all three repos:

```bash
grep -rEn "process\.env\.[A-Z0-9_]+" --include=*.ts --include=*.tsx <repo>
grep -rEn "os\.(environ|getenv)" --include=*.py <repo>
```
