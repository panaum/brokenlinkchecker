# LinkSpy Detail Standard

These rules apply to **all** frontend work by default. They exist because the
difference between a tool and an instrument is the detail. When you add or
change UI, meet these — or say explicitly why an exception is warranted.

Shared primitives live in [`frontend/lib/format.ts`](frontend/lib/format.ts),
[`frontend/lib/useDynamicFavicon.ts`](frontend/lib/useDynamicFavicon.ts), and
[`frontend/components/detail/Bits.tsx`](frontend/components/detail/Bits.tsx).
Reach for those before writing new formatting logic.

Global bans (never violate): no sound/audio; no second theatrical animation (the
radar scan is the only show); nothing below the established contrast/type floors;
every new animation respects `prefers-reduced-motion`. The accent is
**violet/indigo** — reserve it for brand / action / interactive; **health status
uses its OWN colors** (green/amber/red/gray) and is never the accent. Every color
comes from a token, so dark and light themes both work.

Status legend below: **✓ applied** · **◐ primitive built, roll out as you touch
surfaces** · **○ documented rule, not yet wired**.

---

### 1. URL truncation — ✓ primitive, ◐ rollout
Middle-truncate every URL so the **domain and the final path segment stay
visible**: `apexure.com/…/pricing-old`. The full URL is a mono tooltip with
one-click copy. Use `<MiddleTruncate url=… />` or `middleTruncateUrl()`. Never
let a URL wrap to three lines or clip its meaningful tail.

### 2. URL diff highlight — ✓ applied (fix suggestions)
A fix never shows two full URLs side by side. Show the shared prefix, the **old
segment struck through**, the **new segment signal-colored**, shared suffix. Use
`<UrlDiff oldUrl newUrl />` / `urlSegmentDiff()`. Applied in `FixPanel`.

### 3. Timestamps — ◐ primitive, partly applied
Relative everywhere ("2h ago"); absolute on hover (`<RelativeTime iso />`).
Digests/emails render in the **recipient's** timezone. An overnight scheduled
scan is phrased **"checked overnight"**, never a raw 3 AM time
(`phraseScheduled()`). Never show a bare ISO string to a user.

### 4. Favicon status — ✓ applied (scanner)
The tab favicon reflects state via a canvas: a rotating radar **during a scan**,
a **green ring when healthy**, a **red dot when the last scan found issues**.
`useDynamicFavicon(state)`. Respects reduced-motion (static arc).

### 5. Latency coloring — ✓ applied (All Links table)
Response time is tinted **green < 300 ms · amber < 1000 ms · red ≥ 1000 ms**,
in mono. Use `latencyColor(ms)` / `<Latency ms />`. (The live scan feed shows
the real SSE progress lines, which don't carry per-link timing — we don't
fabricate it.)

### 6. Clipboard — ✓ primitive, ◐ rollout
Every copy writes **both** `text/html` and `text/plain` so a paste lands
formatted in Gmail and clean in Slack/editors (`copyRich(text, html)`). The copy
icon **morphs to a check for 800 ms** (`<CopyButton />`, `<MiddleTruncate />`).

### 7. Empty states — ✓ applied, ◐ rollout
One crafted line in product voice + one action, per context. Established copy:
- no scans: **"No targets on watch. Add a site to begin surveillance."**
- no issues: **"All clear. {N} links verified."**
- unverifiable: **"{N} links couldn't be confirmed — providers blocked the
  check. Not necessarily broken."** (teaches the concept at first contact)
No illustrations, no walls of text.

### 8. Scan resume — ○ documented, frontend-resilience partial
On an SSE disconnect, auto-reconnect and resume, with a banner
**"connection recovered — resuming at {n}/{total}"**. If unrecoverable, offer
**partial results** with an honest note of coverage. Backend: scan progress
keyed by scan id so a reconnect can replay (additive endpoint). *Status: the
`/api/prewarm` groundwork is in; full replay-on-reconnect is a follow-up — do
not claim resume works until the backend keys progress by scan id.*

### 9. Number discipline — ✓ applied, ◐ audit ongoing
Tabular numerals **everywhere** (`.font-mono` / `.tabular`). Count containers
are fixed-width so 9→10 shifts nothing. Count-ups run a **constant 600 ms**
regardless of magnitude. Deltas are **always signed and semantically colored**:
for **issue** metrics a decrease is GREEN (−4 is good), an increase RED; for
**health** metrics it's inverted. Use `<Delta value kind="issue"|"health" />` —
it encodes the inversion so you can't get it backwards. Audit every delta you
add against this.

### 10. Hover pre-warming — ◐ partial
Hovering an action pre-resolves its work: site cards prefetch the detail route
(Next `<Link>` default prefetch); a Re-scan hover can fire a HEAD warmup;
Download Fix Pack can begin zip generation on hover (backend idempotent
pre-generate). Never duplicate work already in flight. *Status: route prefetch
is on; fix-pack pre-generate is a documented follow-up.*

### 11. 404 page — ✓ applied
**"This page is broken. Ironic."** + one button, **"Scan your site instead."**
(`app/not-found.tsx`).

### 12. Focus & state restoration — ○ documented
Expanding / re-checking / closing a finding returns focus to the **exact row**
with scroll intact. Table filters live in **URL query params** (shareable,
bookmarkable, back-button-safe). *Status: keyboard triage tracks row focus;
filter-state-in-URL on the scanner is a documented follow-up (deferred to avoid
destabilizing the scanner's streaming state) — wire it with `replaceState` +
hydrate-on-mount when that page is next refactored.*

### 13. Optimistic verify — ✓ applied
Re-check strikes the row immediately (**"verifying…"**), then resolves with a
**fade** + tally increment, or **snaps back with a shake** if still broken.
Never a full-page state change. Applied in `FixPanel` (`.ds-verifying`,
`.ds-resolving`, `.ds-shake`).

### 14. In-app changelog — ✓ applied
A **"What's new" dot** on the nav after a deploy; one line per change,
dismissible, read-flag stored locally (`components/Changelog.tsx`). Bump the top
entry `id` on each deploy.

### 15. Anticipatory scan start — ✓ applied
Pasting/typing a valid URL triggers a **cheap, idempotent backend pre-warm**
(DNS/first-byte) so the scan feels instant on click (`GET /api/prewarm`, debounced
in `UrlInput`). It **never scans** without the click.

---

## Motion & tokens (recap)
- One easing curve: `--ease-out-quart`, used exclusively. All motion ≤ 300 ms
  except the 600 ms score reveal.
- One accent color (`--signal`, violet/indigo) — brand, primary action, links,
  focus, interactive highlight. Never a status.
- Health has its own language, independent of the accent: **green** healthy ·
  **amber** attention · **red** broken · **gray** neutral / unverifiable / first
  scan (never styled as a warning).
- Two themes: dark (default) and an opt-in light theme, both driven entirely by
  the surface/text/status tokens under `:root` / `:root[data-theme="light"]`.
- Data in mono with tabular numerals; display type in Bricolage Grotesque; body
  in Familjen Grotesk.
- Cards lift a visible step above the page; hairline borders with slight
  luminosity; atmosphere at whisper volume.

When a change bounds coverage (truncation, sampling, a cap), say so in the UI —
silent truncation reads as "we covered everything" when we didn't.
