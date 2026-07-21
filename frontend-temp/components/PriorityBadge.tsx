"use client";

import { LinkPriority } from "@/types";

interface PriorityBadgeProps {
  priority?: LinkPriority;
}

const PRIORITY_CONFIG: Record<string, { label: string; color: string; bg: string; emoji: string }> = {
  critical: { label: "Critical", color: "#e05c5c", bg: "rgba(224,92,92,0.12)", emoji: "🔴" },
  high: { label: "High", color: "#f5a623", bg: "rgba(245,166,35,0.12)", emoji: "🟠" },
  medium: { label: "Medium", color: "#f5a623", bg: "rgba(245,166,35,0.10)", emoji: "🟡" },
  low: { label: "Low", color: "#5b8def", bg: "rgba(91,141,239,0.12)", emoji: "🔵" },
};

export default function PriorityBadge({ priority }: PriorityBadgeProps) {
  const cfg = PRIORITY_CONFIG[priority ?? "low"] ?? PRIORITY_CONFIG.low;

  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full select-none"
      style={{
        background: cfg.bg,
        color: cfg.color,
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
