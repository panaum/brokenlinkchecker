export type LinkLabel =
  | 'ok'
  | 'broken'
  | 'redirect'
  | 'blocked'
  | 'forbidden'
  | 'timeout'
  | 'error'
  | 'dead_cta'

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
