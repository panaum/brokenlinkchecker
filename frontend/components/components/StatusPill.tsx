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
    color: "#4ade80",
    bg: "rgba(74,222,128,0.12)",
    dot: "#4ade80",
    tooltip: "This link works perfectly.",
  },
  broken: {
    pill: "Page Not Found",
    color: "#f87171",
    bg: "rgba(248,113,113,0.12)",
    dot: "#f87171",
    tooltip:
      "This page doesn't exist anymore. The link should be removed or updated.",
  },
  redirect: {
    pill: "Redirected",
    color: "#fb923c",
    bg: "rgba(251,146,60,0.12)",
    dot: "#fb923c",
    tooltip:
      "This link forwards to a different URL. Consider updating it to point directly to the final destination.",
  },
  blocked: {
    pill: "Can't Verify",
    color: "#e879f9",
    bg: "rgba(232,121,249,0.12)",
    dot: "#e879f9",
    tooltip:
      "This site blocked our automated check. The link is probably fine — LinkedIn and Cloudflare-protected sites often do this.",
  },
  forbidden: {
    pill: "Can't Verify",
    color: "#e879f9",
    bg: "rgba(232,121,249,0.12)",
    dot: "#e879f9",
    tooltip:
      "This site blocked our automated check. The link is probably fine — LinkedIn and Cloudflare-protected sites often do this.",
  },
  timeout: {
    pill: "Not Responding",
    color: "#94a3b8",
    bg: "rgba(148,163,184,0.12)",
    dot: "#94a3b8",
    tooltip:
      "The site didn't respond in time. It may be down or very slow.",
  },
  error: {
    pill: "Connection Failed",
    color: "#f87171",
    bg: "rgba(248,113,113,0.12)",
    dot: "#f87171",
    tooltip:
      "We couldn't connect to this site. It may have an SSL issue or be offline.",
  },
  dead_cta: {
    pill: "Dead Button",
    color: "#fbbf24",
    bg: "rgba(251,191,36,0.12)",
    dot: "#fbbf24",
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
