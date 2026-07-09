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
  "detected_builders": ["Elementor", "Gutenberg"],  // NEW — may be []
  "pages_scanned": 12,                              // /scan-site only
  "data": [ /* LinkResult[] */ ]
}
```

`detected_builders` lists the page builders fingerprinted on the page (site
scans union the builders found across all pages, in first-seen order).

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
| `broken` | provable failure | HTTP 404/410/5xx, DNS failure, connection refused |
| `dead_cta` | CTA-styled element leading nowhere useful | placeholder hrefs (`#`, `javascript:void(0)`, empty), placeholder domains, broken in-page anchors, handler-less buttons — **high/medium confidence only** |
| `unverifiable` | honest "can't judge from here" | 401/403/405/429/999, bot-blocked, timeouts, elements inside JS-hydrated subtrees (Astro islands), all low-confidence dead-CTA candidates, SPA pages |
| `ok` | healthy | 2xx/3xx — belongs to no issue bucket |

**The governing rule:** when the tool is not sure, the item goes to
`unverifiable`, never to a red bucket. This is a client-facing QA tool, and a
false alarm is worse than a soft warning.

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
