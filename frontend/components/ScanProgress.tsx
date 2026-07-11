"use client";

import { motion } from "framer-motion";
import { X } from "lucide-react";

interface ScanProgressProps {
  message: string;
  percent: number;
  checkedCount?: number;
  totalCount?: number;
  // Accepted for compatibility; the linear bar doesn't render a feed.
  feed?: string[];
  onCancel?: () => void;
}

// A single, straight progress line: the message, a horizontal bar that fills as
// the scan proceeds, the count, and a cancel. No radar.
export default function ScanProgress({
  message,
  percent,
  checkedCount,
  totalCount,
  onCancel,
}: ScanProgressProps) {
  const pct = Math.max(0, Math.min(100, percent));

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.25, ease: [0.165, 0.84, 0.44, 1] }}
      className="ds-container"
      style={{ maxWidth: 720, padding: "0 24px", marginTop: 16 }}
    >
      <div className="ds-card ds-card-pad" style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
        {/* Message + count */}
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
          <span className="ds-text-secondary" style={{ fontSize: "var(--text-body)", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {message || "Scanning…"}
          </span>
          <span className="font-mono ds-text-primary" style={{ fontSize: "var(--text-body)", fontWeight: 600, flexShrink: 0 }}>
            {checkedCount !== undefined && totalCount ? `${checkedCount} / ${totalCount}` : `${pct}%`}
          </span>
        </div>

        {/* The straight progress line */}
        <div style={{ height: 8, borderRadius: 999, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
          <div
            className="progress-fill"
            style={{
              height: "100%",
              borderRadius: 999,
              width: `${pct}%`,
              background: "var(--signal-gradient)",
            }}
          />
        </div>

        {onCancel && (
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button
              onClick={onCancel}
              className="ds-btn-ghost"
              style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 12px", fontSize: "var(--text-caption)" }}
            >
              <X size={13} /> Cancel scan
            </button>
          </div>
        )}
      </div>
    </motion.div>
  );
}
