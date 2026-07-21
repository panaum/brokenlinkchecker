"use client";

import { LinkLabel } from "@/types";
import Tooltip from "./Tooltip";

interface StatusPillProps {
  label: LinkLabel;
  statusCode?: number | null;
}

interface StatusConfig {
  pill: string;
  color: string;
  bg: string;
  dot: string;
  tooltip: string;
}

const STATUS_CONFIG: Record<LinkLabel, StatusConfig> = {
  ok: {
    pill: "Working",
    color: "#4caf7d",
    bg: "rgba(76,175,125,0.12)",
    dot: "#4caf7d",
    tooltip: "This link works perfectly.",
  },
  broken: {
    pill: "Page Not Found",
    color: "#e05c5c",
    bg: "rgba(224,92,92,0.12)",
    dot: "#e05c5c",
    tooltip:
      "This page doesn't exist anymore. The link should be removed or updated.",
  },
  redirect: {
    pill: "Redirected",
    color: "#f5a623",
    bg: "rgba(245,166,35,0.12)",
    dot: "#f5a623",
    tooltip:
      "This link forwards to a different URL. Consider updating it to point directly to the final destination.",
  },
  blocked: {
    pill: "Can't Verify",
    color: "#4f46e5",
    bg: "rgba(79,70,229,0.12)",
    dot: "#4f46e5",
    tooltip:
      "This site blocked our automated check. The link is probably fine — LinkedIn and Cloudflare-protected sites often do this.",
  },
  forbidden: {
    pill: "Can't Verify",
    color: "#4f46e5",
    bg: "rgba(79,70,229,0.12)",
    dot: "#4f46e5",
    tooltip:
      "This site blocked our automated check. The link is probably fine — LinkedIn and Cloudflare-protected sites often do this.",
  },
  timeout: {
    pill: "Not Responding",
    color: "#7a7a8c",
    bg: "rgba(122,122,140,0.12)",
    dot: "#7a7a8c",
    tooltip:
      "The site didn't respond in time. It may be down or very slow.",
  },
  error: {
    pill: "Connection Failed",
    color: "#e05c5c",
    bg: "rgba(224,92,92,0.12)",
    dot: "#e05c5c",
    tooltip:
      "We couldn't connect to this site. It may have an SSL issue or be offline.",
  },
  dead_cta: {
    pill: "Dead Button",
    color: "#f5a623",
    bg: "rgba(245,166,35,0.12)",
    dot: "#f5a623",
    tooltip:
      "This button or CTA has no destination — it goes nowhere when clicked.",
  },
};

export default function StatusPill({ label }: StatusPillProps) {
  const cfg = STATUS_CONFIG[label] ?? STATUS_CONFIG.error;

  return (
    <Tooltip content={cfg.tooltip}>
      <span
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium cursor-default select-none"
        style={{
          background: cfg.bg,
          color: cfg.color,
          fontFamily: "var(--font-poppins), Poppins, sans-serif",
          fontWeight: 500,
          fontSize: "12px",
          border: `1px solid ${cfg.color}22`,
        }}
      >
        <span
          className="w-1.5 h-1.5 rounded-full shrink-0"
          style={{ background: cfg.dot }}
        />
        {cfg.pill}
      </span>
    </Tooltip>
  );
}
