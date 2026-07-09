import { Bucket, LinkResult } from '@/types'

/**
 * Resolve a result's triage bucket.
 *
 * Scans saved before the bucket field existed carry only a `label`, so fall
 * back to deriving it — the same mapping the backend uses in checker.py. When
 * we cannot tell, the result is `unverifiable`: a false alarm in a client-facing
 * report is worse than a soft warning.
 */
export function bucketOf(r: LinkResult): Bucket {
  if (r.bucket) return r.bucket

  switch (r.label) {
    case 'ok':
    case 'redirect':
      return 'ok'
    case 'broken':
    case 'error':
      return 'broken'
    case 'dead_cta':
      // Legacy dead-CTA rows had no confidence; treat low as unverifiable.
      return r.confidence === 'low' ? 'unverifiable' : 'dead_cta'
    default:
      return 'unverifiable'
  }
}

export function inBucket(results: LinkResult[], bucket: Bucket): LinkResult[] {
  return results.filter((r) => bucketOf(r) === bucket)
}

export interface BucketCounts {
  broken: number
  dead_cta: number
  unverifiable: number
}

export function countBuckets(results: LinkResult[]): BucketCounts {
  return {
    broken: inBucket(results, 'broken').length,
    dead_cta: inBucket(results, 'dead_cta').length,
    unverifiable: inBucket(results, 'unverifiable').length,
  }
}

/** "🏗️ Built with: Elementor · 47 links scanned · 2 broken · 1 dead CTA · 3 unverifiable" */
export function buildSummaryLine(
  results: LinkResult[],
  detectedBuilders: string[],
): string {
  const { broken, dead_cta, unverifiable } = countBuckets(results)
  const parts: string[] = []

  if (detectedBuilders.length > 0) {
    parts.push(`🏗️ Built with: ${detectedBuilders.join(', ')}`)
  }
  parts.push(`${results.length} links scanned`)
  parts.push(`${broken} broken`)
  parts.push(`${dead_cta} dead CTA${dead_cta === 1 ? '' : 's'}`)
  parts.push(`${unverifiable} unverifiable`)

  return parts.join(' · ')
}
