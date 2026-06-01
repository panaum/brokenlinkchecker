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
  priority?: LinkPriority
  suggestion?: LinkSuggestion | null
  impact?: BusinessImpact
  first_seen_at?: string
  days_broken?: number
}

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
