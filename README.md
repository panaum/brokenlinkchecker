# LinkSpy

A marketing site can be completely broken and still return HTTP 200 on every
page. The "Book a demo" button has no `href`. The contact form posts to a
deleted endpoint. The Meta pixel is loaded twice, so every conversion is counted
twice. A Google Ad points at a page that 404s and the spend keeps going out. The
SSL certificate expires in nine days.

None of that shows up in uptime monitoring. None of it errors. Nobody finds out
until a client asks why the leads stopped.

LinkSpy is built on the observation that the expensive failures on a
lead-generation site are the silent ones, and that the party who notices last is
the agency that built the site.

**~52,000 lines · 113 backend routes · 15 pages · 973 backend tests.**

---

## What it catches that other tools don't

- **Dead CTAs** — anchors and buttons styled as calls to action with nowhere to
  go, separated from JavaScript-driven UI that merely looks inert.
- **Broken forms**, audited without ever being submitted — across every frame,
  so HubSpot, Typeform and Jotform iframes are found too.
- **Cross-page fragments** — `/about/#team` returns 200 whether or not `#team`
  exists. HTTP can never see this; LinkSpy searches the body it already has.
- **Tracking and pixel integrity** — the same pixel loaded twice, a form with no
  tracking at all, UTMs dropped across a redirect, a thank-you page with no
  conversion event.
- **Ad destinations that have gone dead**, with spend at risk computed from your
  own imported cost figures.
- **Consent-banner behaviour** under reject, accept, GPC and opt-out.
- **Shared third-party outages** correlated across every client at once, so one
  dead Calendly raises one alert naming everyone affected rather than eight
  separate mysteries.
- **Sustained performance regressions**, with a named list of what changed in
  the window.

The discipline underneath all of it: **a thing LinkSpy cannot prove is broken is
reported as `unverifiable`, never red.**

---

## Scanning

Paste a URL and watch the progress stream, or scan a whole site — sitemap
discovery with a depth-2 crawl fallback, up to 200 pages, five at a time.

**Every link is filed by zone** — navigation, header, footer, CTA, body, other —
and a URL appearing in several zones is fetched once but carries every
placement, so the report reads "21 unique links across 71 placements". Zone
drives triage priority.

**It checks far more than `<a href>`:** scripts, stylesheets, images, iframes,
media, favicons, meta images, and CSS `url()` references read from the
stylesheets the browser actually loaded. A 404 script leaves a page returning
200 while nothing on it works.

**Broken means provable.** 404, 410, other 4xx and 5xx, and a hostname confirmed
not to resolve. Everything else — 401, 403, 405, 429, timeouts, bot blocks,
redirect loops, JS-gated fragments — is `unverifiable`, which warns without
crying wolf. For a client-facing QA tool a false alarm costs more than a soft
warning.

**Dead-CTA detection runs six suppression layers**, because a menu toggle and a
broken button look identical in the DOM. A runtime listener probe, declarative
attributes, interactive ARIA roles, widget-context keywords, ~26 page-builder
profiles, and a confidence downgrade on SPAs and Astro islands. A link pointing
at `example.com` stays high confidence regardless, because hydration degrades an
inference about a handler, not a content defect.

**Politeness is adaptive.** Twenty concurrent checks globally, four per domain, a
randomised inter-request gap, and a per-domain penalty that grows on transport
failure and halves on success. A `ConnectError` is only provisionally broken —
the resolver is asked directly before any domain is called dead.

**Every scan diffs against the last one.** New, recurring, fixed. Recurring
findings keep their original `first_seen_at`, which is what makes "broken for 12
days" possible at all. A failed baseline lookup reports `unavailable`, never
`first_scan` — telling someone who has scanned fifty times that there's nothing
to compare against would be worse than saying nothing.

---

## Monitoring and alerting

Per-site cadence — hourly, daily or weekly — on a scheduler inside the
always-on service. Jobs coalesce, so a scan missed across a restart runs once on
resume rather than once per hour it was down, and a duplicate-fire guard makes a
scheduled scan idempotent across a redeploy.

**Three alerting disciplines**, stated in the code and enforced by it:

1. **Silent by default.** No news is the healthy case.
2. **Never alert on doubt.** An `unverifiable` finding never wakes anyone.
3. **Never alert on a blip.** Each new break is re-checked once, and a break
   whose recheck comes back healthy *or merely unverifiable* is dropped.

"Run a check now" runs the exact scheduler code path and explains what it
decided — *"Nothing changed since the last scan, so no alert was sent; this is
the healthy, silent case."*

**Disaster Sentinel** watches SSL expiry, domain expiry over RDAP, indexability,
and uptime every five minutes. Expiry dates are never fabricated: a TLD that
hides expiry surfaces as "unavailable", not a guess. A site is down only after
two consecutive failed pings.

**The third-party watchdog** inventories external hosts across every client.
When a shared host fails across sites it raises one alert naming every affected
client, deduped for 24 hours — and demotes the failure *before* the diff and the
health score, so a dead Calendly never reddens a client's report or dents their
score while the outage is still reported where it belongs.

---

## Forms and lead capture

**The form audit never submits.** There is no `.submit()`, no `.requestSubmit()`,
no `.click()` and no synthetic event anywhere in the collection script. The
listener probe records that a submit handler was *registered*; the tracking
observer wraps `gtag`, `fbq` and `dataLayer.push` to record calls and never
fires one. Auditing a client's contact form must not spam their CRM.

**Almost no status code can prove a form is broken.** The naive rule — action
URL doesn't return 200 — flags nearly every form on the internet, because real
endpoints answer 405 to a GET. That mistake shipped three times, as 405, then
500, then 404, each time fixed by special-casing one more status, which
guaranteed a fourth. So the rule is inverted: exactly two things prove a form
posts nowhere, a host that doesn't resolve and a 410 Gone. A property test
sweeps every status from 100 to 599 and fails the build if anything else ever
reaches a red bucket.

**Form contracts** define what an intact lead is. Observe a form, save a draft,
an operator confirms it into an immutable version, and any later page is
drift-checked against it. Attribution fields — `gclid`, `fbclid`, `msclkid`,
`utm_*` and the rest — are recognised as high severity, because losing one
silently breaks ad attribution without breaking the form.

**Formless capture is found too** — lead-capture UI with no `<form>` tag — and
CTAs that build a form on click are pressed with a six-click, twenty-second
budget, polling for new fields rather than guessing a delay.

**Active form testing** is the one capability that creates real submissions, and
it is off by default behind six mandatory rails: a global flag, per-form human
opt-in with no bulk switch anywhere, payment forms hard-refused regardless of
opt-in, honeypots and hidden fields never filled, exactly-once enforced at
runtime by a guard that raises on a second call, and never scheduled — which a
test enforces by asserting the scheduler cannot even import it.

**The lead tracer** proves end-to-end delivery: submit a flagged test lead,
verify field-by-field arrival in HubSpot or GoHighLevel, delete the test contact,
and write one immutable ledger row for every branch. Enrollment requires a typed
acknowledgment. The first run is forced to be a dry run. Cleanup is mandatory —
a failed delete is a loud outcome naming the contact so a human can remove it.

---

## Consent

The engine observes and records technical behaviour and **never says compliant
or non-compliant.** Every surface carries a scope statement. That rule is the
first thing in the verdict module, and it is the reason the feature can exist at
all: a technical tool giving compliance advice is giving unlicensed legal advice.

Pages are loaded fresh in five modes — cold, reject, accept, GPC, opt-out — and
every third-party request is recorded with its consent class and timing. Named
adapters handle OneTrust, Cookiebot, CookieYes, Termly and HubSpot; an unknown
CMP is never guessed at, and a banner that is present but not operable is
recorded as a *declared limitation*, which is materially different from "no
banner".

Hosts are classified as essential, analytics, advertising/adtech or functional,
and every row states **why** — the table carries a version, so a reclassification
is visible rather than silent.

Verdicts run per regime, UK and US, over observation codes like
`pre_consent_fire`, `post_reject_fire`, `gpc_not_honored` and `optout_dead`.
Drift — something newly appearing — is separated from a continuous finding.

The quarterly **attestation** produces the artifact procurement asks for, with a
coverage-honesty block naming what was *not* checked, a content hash over the
canonical document, and both engine and classification versions recorded.

Enrollment tells the operator the truth to their face: *"The consent ledger
begins recording now; earlier behaviour cannot be backfilled."*

---

## Self-heal

LinkSpy opens pull requests against real repositories, so it does the least it
can, only where explicitly allowed, only for fixes it can prove, and **it never
merges.**

Triggered only by a human, one page at a time. Three rails are checked before
any work happens, including before the scan: the flag must be on, the repo must
be an *exact* member of the allowlist — no wildcards, no same-org inference — and
a token must be present.

**Only two fix classes, both provable.** A permanent redirect chain proves
`old → new`, and only 301 or 308 qualifies, because a 302 is temporary and must
never be baked into source. And mixed content, where an `http://` asset on an
`https://` page has a verified `https://` equivalent.

Every new target is re-checked live, seconds before the PR opens, through the
same single-link checker a scan uses. A fix that cannot be verified is not
proposed. Occurrences are located by walking the git tree rather than GitHub code
search, which doesn't index a fresh repo for minutes to hours. Edits are packed
into pull requests of at most fifty changed lines. The branch is guarded against
ever being the default branch.

**It refuses to touch** anything under `.github/`, CI config, Dockerfiles,
Makefiles, any executable extension, dependency manifests, and config-shaped
JSON. `is_blacklisted_path("")` returns true — it fails closed.

**The prohibition on merging is structural.** Three tests read the module source
and fail the build if a merge call appears anywhere in the three self-heal
modules.

The PR body is an audit trail: every change states its finding, its proof as a
full redirect hop chain with statuses, and its verification timestamp — plus a
rollback note and the exact minimum token scopes the tool requires.

---

## Reporting

**Fix packs** bundle a CSV, per-page instructions, the redirect ruleset and a
readme. **Fix instructions** are deterministic — twelve builder templates plus a
generic fallback, selected by detected platform. There is no model in that file
and there never will be; the single inference is a fuzzy match, gated on
threshold and length ratio, validated as a safe URL, and always labelled as a
suggestion a human confirms.

**Client messages** are written for a business owner rather than a developer,
carrying an age phrase — "it has been like this for 12 days".

**Fix verification** re-checks one finding live and flips it to `verified_fixed`
only on a clean check. A dead CTA honestly reports that a button with no
destination cannot be re-checked by fetching a URL. If the live check passes but
the database write fails, the response explicitly does not claim it saved.

**Vigilance reports** are monthly proof of work: caught-and-fixed timeline,
uptime, forms audited, integrations watched, ads verified, disasters watched, and
measured real-visitor impact. Dollar figures appear only when economics data was
supplied — the line is omitted rather than invented. Server-log demand counts as
a real visitor; Googlebot never does.

**Public reports** share by unguessable revocable token. An **embeddable badge**
renders the score as SVG, grey when never scanned.

**The fragility score** reads findings history longitudinally — which sites
break, how often, and where. A score without reasons is astrology, so it always
returns its contributing factors, and every driver is capped so one extra finding
nudges a few points rather than jumping a band. The client-facing version shows
only an improvement story, only when enabled, and returns nothing at all if the
trend is flat or worse. The word "brittle" never reaches a client.

**The performance ledger** finds sustained regressions — both a 25% and a 150 ms
gate, sustained across three scans, against the median of the three before — and
lists what changed in the window without ever asserting causation. Confidence is
labelled `likely`, `multiple` or `none`.

---

## Integrations

**The QA bridge** exposes live verification status to a separate deliverables
app: is this page still true today? It reads stored results only — it never
triggers a scan. Verdicts are `holding`, `failing` or `couldnt_verify`, and a
check with no signal is omitted entirely rather than stubbed as "not monitored".
Service keys are hashed at rest and shown exactly once.

**Presence** publishes read-only signals — open incidents, checks needing
attention — reduced worst-of, never into a composite. A healthy site yields zero
signals and the consumer renders nothing: there is no "all good" state, by
design, so a usually-empty strip is one people actually read.

**The spine** carries HMAC-signed events between apps with a ±300-second skew
window and an idempotent inbox. The signature covers the exact bytes on the wire,
so re-serialisation cannot break it, and the contract file is duplicated verbatim
in both repositories behind a checksum that must match.

**The quality flywheel** classifies a resolved incident's coverage gap
deterministically — drift, process, or uncovered — and drafts a checklist
candidate for the QA app. No model. A promoted check with no probe behind it
becomes a manual follow-up rather than auto-building one. Nothing is keyed to an
individual developer: the data is for process, not blame.

---

## The Chrome extension

A standalone Manifest V3 extension with no backend and no auth. Scans on page
load, underlines links inline by status, and shows a draggable summary panel in a
Shadow DOM. A mutation observer catches links added after load and SPA route
changes. All fetching happens in the service worker, because content scripts are
subject to CORS and the worker isn't.

Its classifier is deliberately coarser than the backend's — no dead-CTA
detection, no DNS confirmation, no fragment validation — and its own readme says
plainly that soft 404s are not detected.

---

## What makes it careful

Every mechanism here is enforced by a guard, a test, or a structural constraint
rather than by a convention somebody has to remember.

**Nothing contaminates what it measures.** During any phase that clicks, the
browser aborts every non-GET request, every request to ~30 analytics and pixel
hosts, and every top-level navigation — and **fails closed**: a request it cannot
classify does not go out. Blocking non-GET alone is insufficient, because a
conversion pixel is a GET. Without this, pressing a CTA to reveal a modal would
log a visitor who doesn't exist and inflate the client's own funnel.

**Two independent click-safety checks must agree**, one evaluated in the page and
one in Python. If either says no, or if asking throws, the element is not
pressed. A guard that fails open is not a guard.

**Generated artifacts can't carry an injection.** Every value in a fix pack came
off a scraped page and is therefore attacker-controlled, so CSV cells beginning
`= + - @` are prefixed, markdown metacharacters are escaped and URLs wrapped, and
redirect rules reject any URL carrying control characters, a non-http scheme, or
an `@` in the netloc that could disguise the real host.

**Credentials are encrypted at rest and redacted in every error path.** CRM
tokens are Fernet-encrypted with a key derived from an existing secret, so
rotating that secret rotates the encryption. Anything token-shaped is scrubbed
before it can be logged or returned, and the CRM error type is always constructed
with an already-redacted message.

**One scan pipeline, not two.** Monitoring drains the same generator the live
stream does, and the flap recheck reuses the same single-link checker — so a
recheck agrees with a scan by construction rather than by maintenance. There is
exactly one URL normaliser in the codebase, on purpose; without that, issues look
new forever and nothing is ever reported as fixed.

**Every risky capability is a flag that defaults off, and off means inert.**
Two routes answer 404 when disabled, so they're indistinguishable from not
existing. One is documented as byte-identical when off. A deploy is not a
behaviour change.

**The API contract is snapshotted** — 27 per-result fields, 11 top-level, 9 diff
fields, with their types. Fields may be added, never removed or retyped. It also
asserts a missing baseline reports `null` rather than `0`, because 0 would claim
we compared.

**Never silent about a skipped write.** A snapshot save with no site id raises
rather than returning quietly, because that used to be the one path producing
zero rows and zero explanation. Missing-migration cases return a 400 naming the
exact migration file to apply, not a 500.

**Staleness over errors.** Cross-app proxies return last-known-good with a stale
flag rather than a 5xx, because a partner being down must not make a working page
look broken.

**Versioned, auditable catalogs.** Rules, classifications, engines and contracts
all carry versions, and the consent table states why each host is classed as it
is. A catalog you can't audit is a catalog you'll fear to change.

**Suggest, never auto-apply.** Cadence changes are suggestions carrying their
evidence. Contracts are drafts a human confirms. Fuzzy matches are labelled.
Machine pre-fills; humans sign.

---

## Built, not yet wired

Stated plainly, because a reader deserves to know which of the above they can
reach today:

- The issue-lifecycle model persists on every scan but no endpoint reads it yet;
  the legacy path still backs the UI.
- Tracer activation, self-heal mixed-content fixes, the redirect-ruleset export
  and expected-tracking-ID configuration are implemented and tested, with no UI
  caller.
- The client portal is gated behind an enforcement flag and refuses to mint a
  client session while that flag is off — deliberately, since with it off the
  backend bypasses scoping.
- Age is not yet fed into business-impact ranking, so the top severity band
  cannot currently be reached.

---

## Stack

**Backend** — FastAPI, Playwright, Supabase/PostgreSQL, APScheduler.
**Frontend** — Next.js 16 App Router, NextAuth, TypeScript.
**Extension** — Manifest V3, no dependencies.

## Tests

973 backend test functions across 56 files, run in CI on every push and pull
request. The distribution follows the risk: 114 for the form audit, 40 each for
monitoring and the fix engine, 37 for the checker, 34 for self-heal. Several are
property tests sweeping every HTTP status, and several read module source to fail
the build if a forbidden call ever appears.
