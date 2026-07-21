"use client";

import { motion } from "framer-motion";
import { LinkResult, ScanDiff } from "@/types";
import { countBuckets, countPlacements } from "@/lib/buckets";

interface ReportHeaderProps {
  results: LinkResult[];
  detectedBuilders: string[];
  diff?: ScanDiff | null;
  /** The Fix Pack is built from the saved scan, so it needs the site. */
  siteId?: string | null;
}

/**
 * Report header:
 *   🏗️ Built with: Elementor · 47 links scanned · 2 broken · 1 dead CTA · 3 unverifiable
 */
export default function ReportHeader({ results, detectedBuilders, diff, siteId }: ReportHeaderProps) {
  if (results.length === 0) return null;

  const { broken, dead_cta, unverifiable } = countBuckets(results);
  const placements = countPlacements(results);

  // A URL linked from both the nav and the footer is one row but two
  // placements. Showing both stops the report from looking like it missed links.
  const countLabel =
    placements > results.length
      ? `${results.length} unique links across ${placements} placements`
      : `${results.length} links scanned`;

  const chips: { label: string; color: string }[] = [
    { label: countLabel, color: "var(--text-muted)" },
    { label: `${broken} broken`, color: "#e05c5c" },
    { label: `${dead_cta} dead CTA${dead_cta === 1 ? "" : "s"}`, color: "#f5a623" },
    { label: `${unverifiable} unverifiable`, color: "#f5a623" },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="w-full max-w-5xl mx-auto mt-8 px-4"
    >
      {/* Every report leads with the diff. */}
      {diff?.summary && (
        <div
          className="mb-2 text-sm font-medium"
          style={{
            color: diff.has_baseline
              ? "var(--text-primary)"
              : diff.baseline_status === "unavailable"
                ? "#f5a623"
                : "var(--text-muted)",
          }}
        >
          {diff.baseline_status === "unavailable"
            ? "Couldn't compare against the previous scan — baseline tracking isn't set up"
            : diff.summary}
        </div>
      )}

      <div className="glass-card px-5 py-4 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
        {detectedBuilders.length > 0 && (
          <span
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium"
            style={{
              background: "rgba(91,141,239,0.12)",
              color: "#5b8def",
              border: "1px solid rgba(91,141,239,0.25)",
            }}
            title={`Detected page builder${detectedBuilders.length > 1 ? "s" : ""}`}
          >
            <span aria-hidden>🏗️</span>
            Built with: {detectedBuilders.join(", ")}
          </span>
        )}

        {siteId && (broken > 0 || dead_cta > 0) && (
          <a
            href={`/api/sites/${encodeURIComponent(siteId)}/fix-pack`}
            className="ml-auto inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium"
            style={{
              background: "rgba(76,175,125,0.12)",
              color: "#4caf7d",
              border: "1px solid rgba(76,175,125,0.25)",
            }}
            title="fixes.csv, instructions.md, and the redirect ruleset"
          >
            <span aria-hidden>⬇</span> Download Fix Pack
          </a>
        )}

        {chips.map((chip, i) => (
          <span key={chip.label} className="inline-flex items-center gap-3">
            {(i > 0 || detectedBuilders.length > 0) && (
              <span aria-hidden style={{ color: "var(--text-muted)" }}>
                ·
              </span>
            )}
            <span style={{ color: chip.color }}>{chip.label}</span>
          </span>
        ))}
      </div>
    </motion.div>
  );
}
