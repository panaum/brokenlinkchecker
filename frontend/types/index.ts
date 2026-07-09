export type LinkLabel =
  | 'ok'
  | 'broken'
  | 'redirect'
  | 'blocked'
  | 'forbidden'
  | 'timeout'
  | 'error'
  | 'dead_cta'

export type LinkPriority = 'critical' | 'high' | 'medium' | 'low'

/** How sure the backend is about a dead-CTA flag. */
export type Confidence = 'high' | 'medium' | 'low'

/**
 * Three-bucket triage taxonomy.
 *  - `broken`       provable failure (404/410/5xx, DNS, connection refused)
 *  - `dead_cta`     CTA-styled element that leads nowhere useful
 *  - `unverifiable` cannot be judged automatically (401/403/429/999, timeouts,
 *                   JS-hydrated subtrees, low-confidence candidates)
 *  - `ok`           healthy link — belongs to no issue bucket
 *
 * When the backend is unsure it emits `unverifiable`, never a red bucket.
 */
export type Bucket = 'broken' | 'dead_cta' | 'unverifiable' | 'ok'

export interface LinkSuggestion {
  suggested_url: string | null
  confidence: number
  reasoning: string
  intent: string
  wayback_existed: boolean
  wayback_last_seen: string | null
  can_auto_fix: boolean
}

export interface LinkResult {
  url: string
  source_element: string
  anchor_text: string
  category: string
  is_external: boolean
  status_code: number | null
  label: LinkLabel
  final_url: string | null
  response_ms: number
  error?: string
  found_on?: string
  found_on_pages?: string[]
  /** null on working links — priority only triages flagged items. */
  priority?: LinkPriority | null
  suggestion?: LinkSuggestion | null
  impact?: BusinessImpact
  first_seen_at?: string
  days_broken?: number
  /** Triage bucket. Older scans predate this field — treat as undefined. */
  bucket?: Bucket
  /** Confidence in a dead-CTA flag. */
  confidence?: Confidence
  /** Human-readable explanation for the flag, e.g. why a CTA looks dead. */
  reason?: string
  /** Every page zone this destination is linked from, not just the primary one. */
  zones?: string[]
  /** How many times this destination is linked on the page. */
  occurrences?: number
  /** What kind of link this is — `contact` and `anchor` are never fetched. */
  link_kind?: LinkKind
  /** The `#fragment` part of the href, if any. */
  fragment?: string
  /** What kind of thing this URL is. A broken script/stylesheet breaks the page. */
  resource_type?: ResourceType
  /** Stable identity across scans. Present on every scanned link. */
  fingerprint?: string
  /** Flagged items only. A working link is not a finding. */
  diff_status?: DiffStatus | null
  /** Days since this finding was first observed. */
  age_days?: number | null
}

/** Where a finding sits relative to the previous scan. */
export type DiffStatus = 'new' | 'recurring'

/**
 * A page references far more than anchors. A 404 on a script or stylesheet
 * breaks the page while it still returns HTTP 200.
 */
export type ResourceType =
  | 'anchor'
  | 'image'
  | 'script'
  | 'stylesheet'
  | 'css_url'
  | 'iframe'
  | 'media'
  | 'meta_image'
  | 'favicon'
  | 'other'

export interface HostCount {
  host: string
  count: number
}

/** A flagged item, tracked across scans by its fingerprint. */
export interface Finding {
  fingerprint: string
  bucket: Bucket
  confidence: Confidence
  url: string
  anchor_text: string
  zone: string
  reason: string
  first_seen_at: string | null
  resolved_at: string | null
  status: 'open' | 'resolved' | 'verified_fixed'
  age_days: number
}

/**
 * Comparison against the previous snapshot.
 *
 * `has_baseline: false` means this is the site's first scan (or the baseline
 * could not be read). Render new/removed link counts as "n/a" — they are null,
 * not zero, because zero would claim we compared and found nothing.
 */
export interface ScanDiff {
  has_baseline: boolean
  /** "3 new · 1 fixed · 7 still open" — leads every report and email. */
  summary: string
  new: number
  fixed: number
  recurring: number
  new_links: number | null
  removed_links: number | null
  /** Fixed findings are absent from `data` — they live here. */
  fixed_findings: Finding[]
}

/**
 * `http`     — fetched over the network
 * `anchor`   — in-page #fragment, resolved against the rendered DOM
 * `contact`  — mailto:/tel:/sms:, syntax-checked but never fetched
 * `dead_cta` — flagged by the detector; has no destination to check
 */
export type LinkKind = 'http' | 'anchor' | 'contact' | 'dead_cta'

/** Payload of the `result` SSE event from /scan and /scan-site. */
export interface ScanResultPayload {
  type: 'result'
  data: LinkResult[]
  health_score: number
  detected_builders?: string[]
  pages_scanned?: number
  /** Unique destinations (rows). */
  total_links?: number
  /** Sum of occurrences — the number a human counts by eye on the page. */
  total_placements?: number
  diff?: ScanDiff
  /** Informational overview panels. */
  link_types?: Partial<Record<ResourceType, number>>
  top_hosts?: HostCount[]
  schemes?: Record<string, number>
}

/** Diff filter in the results toolbar, alongside the bucket filters. */
export type DiffFilter = 'all' | 'new' | 'recurring' | 'fixed'

export interface BusinessImpact {
  score: number
  level: 'Critical' | 'High' | 'Medium' | 'Low'
  color: string
  description: string
}

export type ZoneFilter =
  | 'Navigation'
  | 'Header'
  | 'Footer'
  | 'CTA'
  | 'Body text'
  | 'Other'
  | 'Dead CTA'

export type FilterType =
  | 'all'
  | LinkLabel
  | ZoneFilter

export type SortOption = 'status' | 'zone' | 'response_ms'

export interface ScanMeta {
  scannedUrl: string
  scannedAt: Date
  pageTitle?: string
}

export interface DashboardScan {
  id: string
  scanned_at: string
  total_links: number
  broken_count: number
  dead_cta_count: number
  health_score: number
}

export interface DashboardSite {
  id: string
  url: string
  name?: string
  client?: string
  freq?: string
  user_email: string
  last_scanned_at: string
  scans: DashboardScan[]
}
