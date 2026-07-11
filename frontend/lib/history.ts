import { DashboardScan, LinkResult } from "@/types";

const DAY_MS = 24 * 60 * 60 * 1000;

// A snapshot has a provable issue if it recorded any broken or dead-CTA finding.
// (Unverifiable never counts against a streak — burden of proof.)
function hasProvableIssue(s: { broken_count?: number; dead_cta_count?: number }): boolean {
  return (s.broken_count ?? 0) > 0 || (s.dead_cta_count ?? 0) > 0;
}

/**
 * "N days clean" — days since the last scan that found a provable issue.
 * Measured from that scan's time to now. If the latest scan still has issues,
 * the streak is 0. If a site has scans but none ever had issues, the streak
 * runs from the first scan. Returns null when there is nothing to measure.
 */
export function cleanStreakDays(scans: DashboardScan[] | undefined, now: number = Date.now()): number | null {
  if (!scans || scans.length === 0) return null;
  const asc = [...scans].sort((a, b) => new Date(a.scanned_at).getTime() - new Date(b.scanned_at).getTime());
  const latest = asc[asc.length - 1];
  if (hasProvableIssue(latest)) return 0;
  // Walk back to the most recent scan that DID have an issue; the streak starts
  // at the first clean scan after it.
  let sinceTime = new Date(asc[0].scanned_at).getTime();
  for (let i = asc.length - 1; i >= 0; i--) {
    if (hasProvableIssue(asc[i])) {
      sinceTime = new Date(asc[i].scanned_at).getTime();
      break;
    }
  }
  return Math.max(0, Math.floor((now - sinceTime) / DAY_MS));
}

/**
 * Approximate "issues fixed this month" across sites: the sum of positive
 * drops in (broken + dead_cta) between consecutive scans dated in the current
 * calendar month. Derived read-only from scan counts — a decrease is a fix.
 */
export function fixedThisMonth(sitesScans: (DashboardScan[] | undefined)[], now: number = Date.now()): number {
  const ref = new Date(now);
  const y = ref.getFullYear();
  const m = ref.getMonth();
  let fixed = 0;
  for (const scans of sitesScans) {
    if (!scans || scans.length < 2) continue;
    const asc = [...scans].sort((a, b) => new Date(a.scanned_at).getTime() - new Date(b.scanned_at).getTime());
    for (let i = 1; i < asc.length; i++) {
      const d = new Date(asc[i].scanned_at);
      if (d.getFullYear() !== y || d.getMonth() !== m) continue;
      const prevIssues = (asc[i - 1].broken_count ?? 0) + (asc[i - 1].dead_cta_count ?? 0);
      const curIssues = (asc[i].broken_count ?? 0) + (asc[i].dead_cta_count ?? 0);
      if (curIssues < prevIssues) fixed += prevIssues - curIssues;
    }
  }
  return fixed;
}

/** Stable identity of a flagged finding within a snapshot's results_json. */
export function findingKey(r: LinkResult): string {
  return r.fingerprint || `${r.url}|${r.anchor_text}`;
}

/** The flagged findings in a snapshot (everything that isn't a healthy link). */
export function flaggedOf(results: LinkResult[] | undefined): LinkResult[] {
  return (results ?? []).filter((r) => r.label !== "ok");
}
