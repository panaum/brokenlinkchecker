"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, BellRing } from "lucide-react";
import { LinkResult, ScanDiff, ScanMeta } from "@/types";

// Numbers never snap — they count up on the one easing curve. Honors
// prefers-reduced-motion (instant).
function useCountUp(target: number, duration = 900): number {
  const [val, setVal] = useState(0);
  const ref = useRef<number>(0);
  useEffect(() => {
    const reduce = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { setVal(target); return; }
    const from = ref.current;
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 4); // ease-out-quart
      const current = Math.round(from + (target - from) * eased);
      setVal(current);
      ref.current = current;
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return val;
}

const EASE = [0.165, 0.84, 0.44, 1] as const;

// Hostname without the www. prefix — "https://www.fautons.com/x" → "fautons.com".
function hostOf(u: string): string {
  try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; }
}

// Relative time — "just now" / "3 min ago" / "2 hr ago" / a date.
function relativeTime(d: Date): string {
  const s = Math.floor((Date.now() - d.getTime()) / 1000);
  if (s < 45) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hr ago`;
  return d.toLocaleDateString();
}

// The post-scan focal point: one plain-English verdict as the largest text on
// the page, a score ring drawing itself in the signal color, the delta vs the
// last scan, and exactly ONE primary action.
export default function ScanVerdict({
  results,
  diff,
  score,
  meta,
  onRescan,
  onViewIssues,
}: {
  results: LinkResult[];
  diff: ScanDiff | null;
  score: number;
  meta?: ScanMeta | null;
  onRescan?: () => void;
  onViewIssues: () => void;
}) {
  const broken = results.filter((r) => r.label === "broken").length;
  const deadCta = results.filter((r) => r.label === "dead_cta").length;
  const issues = broken + deadCta;
  const hasIssues = issues > 0;
  const shownScore = useCountUp(score);

  let verdict: string;
  if (broken > 0) {
    verdict = `${broken} broken ${broken === 1 ? "link is" : "links are"} turning visitors away.`;
  } else if (deadCta > 0) {
    verdict = `${deadCta} call-to-action${deadCta === 1 ? "" : "s"} ${deadCta === 1 ? "leads" : "lead"} nowhere.`;
  } else {
    verdict = "All clear — no broken links on watch.";
  }

  const hasBaseline = Boolean(diff?.has_baseline);

  // Score ring geometry. Draws itself via stroke-dashoffset (600ms). The ring
  // and numeral are BRAND purple — identity, not a status. Health is conveyed by
  // the verdict sentence and the issue counts, not the score's color.
  const R = 20; // ~46px outer diameter (2·R + strokeWidth)
  const C = 2 * Math.PI * R;
  const ringColor = "var(--signal)";

  const rise = (delay: number) => ({
    initial: { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.32, ease: EASE, delay },
  });

  return (
    <section style={{ position: "relative" }}>
      {/* soft radial glow behind the verdict block */}
      <div style={{ position: "absolute", inset: 0, pointerEvents: "none", background: "radial-gradient(600px 200px at 20% 40%, rgba(79,70,229,0.08), transparent 70%)" }} />
      <div
        style={{ padding: "var(--space-6)", display: "flex", alignItems: "center", gap: "var(--space-6)", flexWrap: "wrap", position: "relative" }}
      >
        {/* Score ring — health-colored, draws itself. ~46px. */}
        <motion.div {...rise(0)} style={{ position: "relative", width: 52, height: 52, flexShrink: 0 }}>
          <svg width="52" height="52" viewBox="0 0 52 52">
            <circle cx="26" cy="26" r={R} fill="none" stroke="var(--border-subtle)" strokeWidth="6" />
            <motion.circle
              cx="26" cy="26" r={R} fill="none"
              stroke={ringColor}
              strokeWidth="6" strokeLinecap="round"
              strokeDasharray={C}
              initial={{ strokeDashoffset: C }}
              animate={{ strokeDashoffset: C * (1 - score / 100) }}
              transition={{ duration: 0.6, ease: EASE, delay: 0.1 }}
              transform="rotate(-90 26 26)"
            />
          </svg>
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <span className="font-mono" style={{ fontSize: 15, fontWeight: 700, color: ringColor, lineHeight: 1 }}>{shownScore}</span>
          </div>
        </motion.div>

        {/* Verdict + delta */}
        <div style={{ flex: 1, minWidth: 260 }}>
          <motion.div {...rise(0.06)} className="font-display ds-text-primary" style={{ fontSize: "var(--text-display)", fontWeight: 700, lineHeight: 1.15 }}>
            {verdict}
          </motion.div>
          <motion.div {...rise(0.12)} style={{ marginTop: 10, fontSize: "var(--text-body)" }}>
            {hasBaseline && diff?.summary ? (
              <span className="ds-text-secondary">Since last scan: <span className="mono">{diff.summary}</span></span>
            ) : (
              <span className="ds-status ds-status-neutral"><span className="ds-status-dot" />First scan — no baseline to compare yet.</span>
            )}
          </motion.div>

          {/* Site · time metadata (moved here from the old PagePreviewCard). */}
          {meta && (
            <motion.div
              {...rise(0.16)}
              className="ds-text-muted"
              style={{ marginTop: 6, fontSize: "var(--text-caption)", fontFamily: "var(--font-poppins), Poppins, sans-serif" }}
            >
              <span className="mono">{hostOf(meta.scannedUrl)}</span> · {relativeTime(meta.scannedAt)}
            </motion.div>
          )}
        </div>

        {/* Actions — Re-scan plus the single primary action. */}
        <motion.div {...rise(0.18)} style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 8 }}>
          {onRescan && (
            <button className="ds-btn-ghost" onClick={onRescan}>Re-scan</button>
          )}
          {hasIssues ? (
            <button className="ds-btn-primary" onClick={onViewIssues} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              View fixes <ArrowRight size={16} />
            </button>
          ) : (
            <Link href="/dashboard" className="ds-btn-primary" style={{ display: "inline-flex", alignItems: "center", gap: 8, textDecoration: "none" }}>
              <BellRing size={16} /> Set up monitoring
            </Link>
          )}
        </motion.div>
      </div>
    </section>
  );
}
