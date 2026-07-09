# Frontend contract

The JSON shape emitted by the FastAPI backend and the UI expectations built on
top of it. The Next.js app in `frontend/` already implements this; the document
exists for any other consumer (the `frontend/app/api/*` proxy routes, exports,
Slack payloads).

## Scan endpoints

`GET /scan?url=…&email=…` and `GET /scan-site?url=…&email=…&max_pages=…` are
Server-Sent Event streams. Three event types:

```jsonc
{ "type": "progress", "message": "Checked 12/40 links...", "percent": 55 }

{ "type": "error", "message": "…" }

{
  "type": "result",
  "health_score": 87,
  "detected_builders": ["Elementor", "Gutenberg"],  // may be []
  "total_links": 21,                                // unique destinations (= data.length)
  "total_placements": 71,                           // sum of occurrences
  "pages_scanned": 12,                              // /scan-site only
  "data": [ /* LinkResult[] */ ]
}
```

`detected_builders` lists the page builders fingerprinted on the page (site
scans union the builders found across all pages, in first-seen order).

`total_links` counts unique destinations — each is fetched once. `total_placements`
counts every `<a>` on the page, which is the number a human gets counting links
by eye. A URL linked from both the nav and the footer is **one row with two
placements**. Render both (`"21 unique links across 71 placements"`), or the
report looks like it lost links.

## LinkResult

Every item carries `bucket`, `confidence`, and `reason`. All pre-existing fields
are unchanged, so older consumers keep working.

```jsonc
{
  "url": "https://acme.test/pricing",
  "source_element": "a",
  "anchor_text": "Buy Now",
  "category": "Dead CTA",          // page zone: Navigation | Header | CTA | Body text | Footer | Other | Dead CTA
  "is_external": false,
  "priority": "medium",            // critical | high | medium | low

  "status_code": 404,              // null for dead CTAs and timeouts
  "label": "broken",               // ok | broken | redirect | blocked | timeout | error | dead_cta
  "final_url": null,
  "response_ms": 231,
  "error": null,

  // ── added by this overhaul ────────────────────────────────────────────────
  "bucket": "broken",              // broken | dead_cta | unverifiable | ok
  "confidence": "high",            // high | medium | low
  "reason": "Anchor href goes nowhere · builder: Elementor",

  "link_kind": "http",             // http | anchor | contact | dead_cta
  "fragment": "",                  // the #fragment part of the href, if any
  "zones": ["Navigation", "Footer"],  // every zone this destination is linked from
  "occurrences": 4,                // how many times it is linked on the page

  // optional enrichment
  "suggestion": null,
  "impact": { "score": 75, "level": "High", "color": "#fb923c", "description": "Fix this week" },
  "found_on_pages": ["/", "/pricing"],
  "first_seen_at": null,
  "days_broken": null
}
```

### The three buckets

| bucket | meaning | contents |
|---|---|---|
| `broken` | provable failure | HTTP 404/410/5xx, or a hostname that does not resolve |
| `dead_cta` | CTA-styled element leading nowhere useful | placeholder hrefs (`#`, `javascript:void(0)`, empty), placeholder domains, broken in-page anchors, handler-less buttons — **high/medium confidence only** |
| `unverifiable` | honest "can't judge from here" | 401/403/405/429/999, bot-blocked, timeouts, elements inside JS-hydrated subtrees (Astro islands), all low-confidence dead-CTA candidates, SPA pages |
| `ok` | healthy | 2xx/3xx — belongs to no issue bucket |

**The governing rule:** when the tool is not sure, the item goes to
`unverifiable`, never to a red bucket. This is a client-facing QA tool, and a
false alarm is worse than a soft warning.

### Link kinds

Every `<a>` a visitor can see is accounted for, but they are not all fetched:

| `link_kind` | what it is | how it's checked |
|---|---|---|
| `http` | an http(s) destination | fetched; if it carries a `#fragment`, the fragment is validated against the response body |
| `anchor` | an in-page `#fragment` | resolved against the rendered DOM; only resolving anchors appear (unresolved ones surface as dead CTAs) |
| `contact` | `mailto:` / `tel:` / `sms:` | syntax-validated, never fetched |
| `dead_cta` | a flagged element | has no destination to check |

A link like `/about-us/#team` returns HTTP 200 whether or not `#team` exists —
HTTP never sees the fragment. The checker validates it against the fetched body,
so a link that silently dumps the visitor at the top of the page is caught.

Two guards keep this from crying wolf:

- **Only identifier-like fragments are checked.** `#url=http%3A%2F%2F…`,
  `#!/dashboard`, and `#/getting-started` carry client-side state or routes;
  they never name an element, so "section not found" would be meaningless.
- **Absence is only provable on a page that runs no JavaScript.** We fetch
  without JS, so any target carrying a `<script>` may build the section at
  runtime. A missing id there yields `bucket: "unverifiable"` with
  `label: "ok"` — the link works, we simply could not confirm the section.

Because of that last case, a row can have `label: "ok"` and
`bucket: "unverifiable"`. **Do not count such a row as working.** `bucket` is
authoritative; `working` should be `label === "ok" && bucket === "ok"`.

### Network errors

No transport error proves a link is broken on its own. Checking hundreds of
links makes servers reset connections and overloads the OS resolver, so a
healthy host raises `ConnectError("getaddrinfo failed")` and a WAF RSTs a
connection exactly like a closed port would.

The one provable case is a hostname that **still fails to resolve when queried
directly** — a dead domain. That yields `bucket: "broken"`. Every other
transport failure (reset, refused, protocol error, SSL, timeout) is
`unverifiable`.

The checker also backs off adaptively: requests are capped per domain, each
transport failure adds a delay for that domain, and each success decays it.
Without this, scanning a 400-link page gets the crawler throttled and every
healthy link is reported as a failure.

`bucket` is authoritative — do not re-derive triage from `label`. A `dead_cta`
label with `bucket: "unverifiable"` is a low-confidence candidate and must be
presented as a soft warning, not a defect. `frontend/lib/buckets.ts` exposes
`bucketOf()`, which also back-fills the bucket for scans saved before the field
existed.

## UI spec

**Report header** — builder badge plus bucket counts:

> 🏗️ Built with: Elementor · 47 links scanned · 2 broken · 1 dead CTA · 3 unverifiable

Omit the badge when `detected_builders` is empty.

**Three result sections**, in this order:

1. **Broken Links** — red, urgent. These fail outright.
2. **Dead CTAs** — orange, actionable. Each row shows a confidence chip
   (`high` / `medium`).
3. **Unverifiable** — yellow/neutral. Copy: *"Couldn't verify automatically —
   please check manually"*. Never styled as an error.

Every item displays its `reason` string. Reasons are suffixed with
`· builder: X` when a page builder was detected, so a reviewer can see which
builder's idioms were considered.

Health score (`health_score`, mirrored by `HealthScore.tsx`) penalizes broken
links (×3), `bucket: "dead_cta"` items (×2), and timeouts (×1). Unverifiable
items cost nothing — we cannot prove they are defects.
