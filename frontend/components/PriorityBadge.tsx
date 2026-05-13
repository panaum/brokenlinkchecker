"use client";

import { LinkPriority } from "@/types";

interface PriorityBadgeProps {
  priority?: LinkPriority;
}

const PRIORITY_CONFIG: Record<string, { label: string; color: string; bg: string; emoji: string }> = {
  critical: { label: "Critical", color: "#f87171", bg: "rgba(248,113,113,0.12)", emoji: "🔴" },
  high: { label: "High", color: "#fb923c", bg: "rgba(251,146,60,0.12)", emoji: "🟠" },
  medium: { label: "Medium", color: "#fbbf24", bg: "rgba(251,191,36,0.12)", emoji: "🟡" },
  low: { label: "Low", color: "#60a5fa", bg: "rgba(96,165,250,0.12)", emoji: "🔵" },
};

export default function PriorityBadge({ priority }: PriorityBadgeProps) {
  const cfg = PRIORITY_CONFIG[priority ?? "low"] ?? PRIORITY_CONFIG.low;

  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full select-none"
      style={{
        background: cfg.bg,
        color: cfg.color,
        fontFamily: "var(--font-poppins), Poppins, sans-serif",
        fontWeight: 500,
        fontSize: "10px",
        border: `1px solid ${cfg.color}22`,
        whiteSpace: "nowrap",
      }}
    >
      {cfg.emoji} {cfg.label}
    </span>
  );
}
