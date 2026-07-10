"use client";

import { motion } from "framer-motion";
import { LinkResult, ScanDiff } from "@/types";
import { countBuckets, countPlacements } from "@/lib/buckets";

interface ReportHeaderProps {
  results: LinkResult[];
  detectedBuilders: string[];
  diff?: ScanDiff | null;
}

/**
 * Report header:
 *   🏗️ Built with: Elementor · 47 links scanned · 2 broken · 1 dead CTA · 3 unverifiable
 */
export default function ReportHeader({ results, detectedBuilders, diff }: ReportHeaderProps) {
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
    { label: countLabel, color: "rgba(255,255,255,0.55)" },
    { label: `${broken} broken`, color: "#f87171" },
    { label: `${dead_cta} dead CTA${dead_cta === 1 ? "" : "s"}`, color: "#fb923c" },
    { label: `${unverifiable} unverifiable`, color: "#fbbf24" },
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
              ? "#e2e8f0"
              : diff.baseline_status === "unavailable"
                ? "#fbbf24"
                : "rgba(255,255,255,0.45)",
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
              background: "rgba(96,165,250,0.12)",
              color: "#93c5fd",
              border: "1px solid rgba(96,165,250,0.25)",
            }}
            title={`Detected page builder${detectedBuilders.length > 1 ? "s" : ""}`}
          >
            <span aria-hidden>🏗️</span>
            Built with: {detectedBuilders.join(", ")}
          </span>
        )}

        {chips.map((chip, i) => (
          <span key={chip.label} className="inline-flex items-center gap-3">
            {(i > 0 || detectedBuilders.length > 0) && (
              <span aria-hidden style={{ color: "rgba(255,255,255,0.25)" }}>
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
