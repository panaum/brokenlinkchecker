"use client";

import React from "react";
import Link from "next/link";
import { ArrowRight, BellRing } from "lucide-react";
import { LinkResult, ScanDiff } from "@/types";

// The post-scan focal point: one plain-English verdict as the largest text on
// the page, a score ring, the delta vs the last scan, and exactly ONE primary
// action. Everything else on the page is subordinate to this block.
export default function ScanVerdict({
  results,
  diff,
  score,
  onViewIssues,
}: {
  results: LinkResult[];
  diff: ScanDiff | null;
  score: number;
  onViewIssues: () => void;
}) {
  const broken = results.filter((r) => r.label === "broken").length;
  const deadCta = results.filter((r) => r.label === "dead_cta").length;
  const issues = broken + deadCta;
  const hasIssues = issues > 0;

  // Verdict sentence — the biggest text in the view.
  let verdict: string;
  let verdictCls: string;
  if (broken > 0) {
    verdict = `${broken} broken ${broken === 1 ? "link is" : "links are"} turning visitors away.`;
    verdictCls = "ds-text-primary";
  } else if (deadCta > 0) {
    verdict = `${deadCta} call-to-action${deadCta === 1 ? "" : "s"} ${deadCta === 1 ? "leads" : "lead"} nowhere.`;
    verdictCls = "ds-text-primary";
  } else {
    verdict = "Everything checks out — no broken links found.";
    verdictCls = "ds-text-primary";
  }

  // Delta vs baseline. No baseline = neutral gray, never a warning.
  const hasBaseline = Boolean(diff?.has_baseline);

  // Score ring geometry.
  const R = 46;
  const C = 2 * Math.PI * R;
  const ringColor =
    score >= 90 ? "var(--status-healthy)" : score >= 70 ? "var(--status-attention)" : "var(--status-broken)";

  return (
    <section className="ds-container" style={{ padding: "0 24px", marginTop: 8 }}>
      <div
        className="ds-card"
        style={{ padding: "var(--space-6)", display: "flex", alignItems: "center", gap: "var(--space-6)", flexWrap: "wrap" }}
      >
        {/* Score ring — one of the only two places the accent gradient appears. */}
        <div style={{ position: "relative", width: 112, height: 112, flexShrink: 0 }}>
          <svg width="112" height="112" viewBox="0 0 112 112">
            <defs>
              <linearGradient id="verdict-ring" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#6d28d9" />
                <stop offset="100%" stopColor="#a855f7" />
              </linearGradient>
            </defs>
            <circle cx="56" cy="56" r={R} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="8" />
            <circle
              cx="56" cy="56" r={R} fill="none"
              stroke={score >= 70 ? "url(#verdict-ring)" : ringColor}
              strokeWidth="8" strokeLinecap="round"
              strokeDasharray={C}
              strokeDashoffset={C * (1 - score / 100)}
              transform="rotate(-90 56 56)"
              style={{ transition: "stroke-dashoffset 600ms cubic-bezier(0.4,0,0.2,1)" }}
            />
          </svg>
          <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontSize: 30, fontWeight: 700, color: ringColor, lineHeight: 1 }}>{score}</span>
            <span className="ds-text-muted" style={{ fontSize: 11 }}>/ 100</span>
          </div>
        </div>

        {/* Verdict + delta */}
        <div style={{ flex: 1, minWidth: 260 }}>
          <div className={verdictCls} style={{ fontSize: "var(--text-display)", fontWeight: 700, lineHeight: 1.15, letterSpacing: "-0.5px" }}>
            {verdict}
          </div>
          <div style={{ marginTop: 10, fontSize: "var(--text-body)" }}>
            {hasBaseline && diff?.summary ? (
              <span className="ds-text-secondary">Since last scan: {diff.summary}</span>
            ) : (
              <span className="ds-status ds-status-neutral"><span className="ds-status-dot" />First scan — no baseline to compare yet.</span>
            )}
          </div>
        </div>

        {/* The single primary action. */}
        <div style={{ flexShrink: 0 }}>
          {hasIssues ? (
            <button className="ds-btn-primary" onClick={onViewIssues} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              View fixes <ArrowRight size={16} />
            </button>
          ) : (
            <Link href="/dashboard" className="ds-btn-primary" style={{ display: "inline-flex", alignItems: "center", gap: 8, textDecoration: "none" }}>
              <BellRing size={16} /> Set up monitoring
            </Link>
          )}
        </div>
      </div>
    </section>
  );
}
