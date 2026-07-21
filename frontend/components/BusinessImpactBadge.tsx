"use client";

import { useState } from "react";
import { BusinessImpact } from "@/types";

interface BusinessImpactBadgeProps {
  impact: BusinessImpact;
}

const LEVEL_STYLES: Record<string, { bg: string; color: string; border: string }> = {
  Critical: {
    bg: "rgba(224,92,92,0.15)",
    color: "#e05c5c",
    border: "0.5px solid rgba(224,92,92,0.4)",
  },
  High: {
    bg: "rgba(245,166,35,0.15)",
    color: "#f5a623",
    border: "0.5px solid rgba(245,166,35,0.4)",
  },
  Medium: {
    bg: "rgba(245,166,35,0.15)",
    color: "#f5a623",
    border: "0.5px solid rgba(245,166,35,0.4)",
  },
  Low: {
    bg: "rgba(122,122,140,0.15)",
    color: "#7a7a8c",
    border: "0.5px solid rgba(122,122,140,0.4)",
  },
};

export default function BusinessImpactBadge({ impact }: BusinessImpactBadgeProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  const style = LEVEL_STYLES[impact.level] ?? LEVEL_STYLES.Low;

  return (
    <div
      className="relative inline-flex"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <span
        className="inline-flex items-center gap-1.5 select-none"
        style={{
          background: style.bg,
          color: style.color,
          border: style.border,
          fontFamily: "var(--font-poppins), Poppins, sans-serif",
          fontSize: "11px",
          fontWeight: 600,
          padding: "2px 8px",
          borderRadius: "999px",
          whiteSpace: "nowrap",
        }}
      >
        <span
          className="w-1.5 h-1.5 rounded-full shrink-0"
          style={{ background: style.color }}
        />
        {impact.level}
      </span>

      {/* Tooltip */}
      {showTooltip && (
        <div
          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50"
          style={{
            background: "var(--surface-card)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "10px",
            padding: "8px 12px",
            minWidth: "160px",
            boxShadow: "var(--elev-3)",
          }}
        >
          <div
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontSize: "12px",
              fontWeight: 600,
              color: style.color,
              marginBottom: 4,
            }}
          >
            {impact.level} Impact — {impact.score}/100
          </div>
          <div
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontSize: "11px",
              fontWeight: 400,
              color: "var(--text-muted)",
              lineHeight: 1.4,
            }}
          >
            {impact.description}
          </div>
          {/* Arrow */}
          <div
            className="absolute top-full left-1/2 -translate-x-1/2"
            style={{
              width: 0,
              height: 0,
              borderLeft: "5px solid transparent",
              borderRight: "5px solid transparent",
              borderTop: "5px solid var(--surface-card)",
            }}
          />
        </div>
      )}
    </div>
  );
}
