# LinkSpy Roadmap

Broken-link / dead-CTA checker → monitoring service. Phases below are ordered
by the revised build sequence, not their original numbers. Each phase is a
parent issue; the checklist items under it are sub-issues / tasks.

Guiding principles (apply to every phase):
- Burden of proof is on "broken". When unsure → `unverifiable`, never red.
- Bot-blocks (403/429/999), timeouts, HEAD-rejected → `unverifiable`.
- No LLM calls in the product path — fixes are deterministic and traceable.
- Risky capabilities (active submission, watchdog alerts, auto-PR) ship behind
  feature flags, default OFF.
- Never take an action a client's systems can't distinguish from a real user.

---

## Phase 8 — Robustness suite  [BUILD FIRST]
**Why first:** "works credibly for all websites" is the actual goal. Everything
else is more trustworthy on top of this.
Status: todo · Flag: n/a · Risk: low

- [ ] Redirect loops: cap at 10 hops → label "redirect loop", not broken
- [ ] Soft 404s: HTTP 200 + not-found title / tiny body → "possible soft 404" (unverifiable)
- [ ] Catch-all redirect to homepage: final path lost → note it, don't call broken
- [ ] Timeout fall-through: pages that never hit networkidle must demonstrably time out cleanly
- [ ] Non-HTML content types (PDF/image/json) = working, never parsed as HTML
- [ ] mailto/tel/sms/data URIs never HTTP-requested
- [ ] SSL cert errors as their own unverifiable sub-status
- [ ] Per-domain concurrency limit + 429 backoff (one rate-limiting domain can't poison the report)
- [ ] Per-page try/except: one page crash → PARTIAL results, that page marked failed (scan NEVER returns zero because page 47 died)
- [ ] Links-per-page cap with coverage note
- [ ] Duplicate DOM ids don't crash the anchor check
- [ ] Unicode / IDN URLs round-trip
- [ ] Tests: all negative cases above pass

---

## Phase 4 — Passive form + tracking audit  [BUILD SECOND]
**Why:** Silent form/CRM breakage is the highest-cost invisible failure for
lead-gen clients. Passive tier is safe and helps every client.
Status: todo · Flag: active submission OFF · Risk: low (passive) / high (active)

- [ ] Passive form audit: `<form>` action present + reachable (reuse checker), method sane, submit control exists, required fields have names, form not hidden under overlay
- [ ] Route form findings: missing/dead action → dead_cta; couldn't check → unverifiable
- [ ] Passive tracking audit: detect GTM/GA4/Meta Pixel per page
- [ ] Flag duplicate pixel IDs on one page
- [ ] Flag pages where a form exists but no tracking script loaded
- [ ] Verify UTM params survive redirect chains (first hop vs final query params)
- [ ] Per-platform static form checks: HubSpot embed script loads, GHL native form, ClickFunnels, Kajabi
- [ ] ACTIVE test submission (opt-in per form, flag OFF): fill "LINKSPY-TEST", skip file inputs, respect honeypots, submit once, record status + thank-you/redirect + tracking event fired
- [ ] Active path REFUSES payment forms (detect card fields / Stripe iframe)
- [ ] Tests: passive on fixtures, honeypot avoidance, payment-form refusal, active path fully mocked

---

## Phase 6 — Fix engine (SLIMMED)  [BUILD THIRD] [HUMAN PASS REQUIRED]
**Revised scope:** Dropped the 72-file per-builder click-by-click library —
"the instructions are common sense". Keep only what's genuinely valuable.
Status: todo · Flag: n/a · Risk: medium (instructions touch live pages)

- [ ] Confident target suggestion: redirect final destination (unambiguous)
- [ ] Confident target suggestion: rapidfuzz closest-live-URL for 404s (SUGGEST only, soft language, never auto-apply)
- [ ] Impact-ranked triage using existing `calculate_business_impact` (CTA/nav/body/footer weighting)
- [ ] One client message per severity — plain language, leads with business consequence, HTML-escaped, CSV-injection-safe
- [ ] Builder gotchas ONLY where non-obvious: GHL Vue-hydration timing, Kajabi content-block stripping, Elementor z-index traps (hand-written, not generated)
- [ ] Fix Pack zip: fixes.csv + instructions.md + redirect rules (escape every field; neutralize =,+,-,@)
- [ ] Fix-verify loop: POST /api/findings/{id}/verify → re-check live → flip to "verified_fixed" + resolved_at (don't lie if still broken)
- [ ] Frontend: "How to fix", "Re-check", "Copy client message", "Download Fix Pack"
- [ ] rapidfuzz added to requirements.txt
- [ ] HUMAN PASS: read generated instructions.md as a client before Phase 7 builds on it
- [ ] Tests: every builder×issue renders (no {braces}), CSV escaping incl. injection payloads, malicious href/anchor rejected, verify loop flips status

---

## Phase 9 — Continuous monitoring  [BUILD FOURTH]  [NEW]
**Why:** Turns a tool-you-run into a service clients pay for monthly.
Status: todo · Flag: n/a · Risk: medium · **BLOCKED: scheduler decision needed**

- [ ] DECISION: scheduler = Supabase pg_cron vs Vercel Cron vs background worker (Railway/Render/GH Actions). Serverless times out on big scans → worker likely needed.
- [ ] Scheduled scan runner: server-side, no SSE, writes snapshot only, driven by `sites.freq`
- [ ] Change-only alerting: reuse diff engine, notify only on new provable breaks or fixes, silence when nothing changed
- [ ] False-positive discipline: unverifiable bucket NEVER triggers an alert
- [ ] Flap protection: confirm a new break with one re-check before alerting
- [ ] Status/history view: "last checked Xh ago, healthy N days" — the sellable uptime record
- [ ] Per-client vigilance digest (weekly): "checked N times, caught X, resolved Y" — justifies the retainer
- [ ] Default clients to DAILY not hourly (24× cost, no real benefit)
- [ ] Tests: scheduler fires on freq, no-change = no alert, flap suppressed, digest renders

---

## Phase 5 — Priority + traffic weighting  [BUILD FIFTH]
**Why:** Enhances triage/comms across all earlier phases. Not blocking.
Status: todo · Flag: n/a · Risk: low

- [ ] Manual per-page tier (high/medium/low) editable in UI
- [ ] CSV import of GSC "Pages" export or GA4 pages export (url + clicks/sessions), parse defensively
- [ ] Store page_weights
- [ ] Deterministic priority = f(bucket, confidence, zone, page weight), documented in code
- [ ] Impact sentence from templates; visits clause ONLY renders when real imported data exists (no invented numbers)
- [ ] Tests: priority formula, CSV parse edge cases, no-data path omits visits clause

---

## Phase 7 — Third-party watchdog + self-heal  [BUILD LAST]
**Split:** Watchdog is a standout feature, build anytime. Auto-PR / self-heal is
narrow and risky — own sites first (Apexure, Fautons), provable fixes only.
Status: todo · Flag: watchdog alerts OFF, GitHub tier OFF · Risk: high (PR tier)

### Watchdog (keep — strong feature)
- [ ] Inventory external script/iframe/asset hosts across ALL scanned sites
- [ ] Alert ONCE when a shared dependency dies across all affected sites, list which clients hit
- [ ] Ties into Phase 4 (embed-script-down detection)

### Self-heal / auto-PR (narrow, own repos only)
- [ ] Repo allowlist, explicit (Apexure, Fautons) — non-listed repo untouchable
- [ ] Auto-draft PROVABLE fixes only: redirect updates, mixed-content (one right answer)
- [ ] 404 fuzzy matches → PR body as SUGGESTION, never auto-applied
- [ ] Never push to default branch; branch `linkspy/fix-{scan_id}`; diff capped ~50 lines
- [ ] `.github/**` blacklisted; never generate executable content
- [ ] Verify-after: confirm new target resolves BEFORE opening PR
- [ ] Never auto-merge — human on the merge button always
- [ ] First version: redirect + mixed-content only, on Apexure
- [ ] Tests: allowlist/blacklist enforcement, diff cap, non-owned-repo rejected, workflow-file edit refused


## Acceptance (whole roadmap)
- [ ] Full pytest suite green, zero skips
- [ ] grep: no anthropic/openai/llm imports in product path
- [ ] Working link → priority=None end-to-end (API + UI)
- [ ] Two scans → diff endpoint correct new/fixed/recurring
- [ ] Broken image/script/stylesheet all detected + typed
- [ ] Fix Pack downloads with fully-rendered instructions.md
- [ ] Fix-verify flips a finding to verified-fixed with timestamp
- [ ] Copy client message renders escaped, client-ready
- [ ] All three flags (active submission, watchdog, GitHub) default OFF; toggling never breaks endpoints