"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, BellRing } from "lucide-react";
import { LinkResult, ScanDiff } from "@/types";

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

// The post-scan focal point: one plain-English verdict as the largest text on
// the page, a score ring drawing itself in the signal color, the delta vs the
// last scan, and exactly ONE primary action.
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

  // Score ring geometry. Draws itself via stroke-dashoffset (600ms).
  const R = 46;
  const C = 2 * Math.PI * R;
  const ringColor =
    score >= 90 ? "var(--signal)" : score >= 70 ? "var(--status-attention)" : "var(--status-broken)";
  const useSignalRing = score >= 70;

  const rise = (delay: number) => ({
    initial: { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.32, ease: EASE, delay },
  });

  return (
    <section className="ds-container" style={{ padding: "0 24px", marginTop: 8, position: "relative" }}>
      {/* soft radial glow behind the verdict block */}
      <div style={{ position: "absolute", inset: 0, pointerEvents: "none", background: "radial-gradient(600px 200px at 20% 40%, rgba(34,211,170,0.07), transparent 70%)" }} />
      <div
        className="ds-card"
        style={{ padding: "var(--space-6)", display: "flex", alignItems: "center", gap: "var(--space-6)", flexWrap: "wrap", position: "relative" }}
      >
        {/* Score ring — signal color, draws itself. */}
        <motion.div {...rise(0)} style={{ position: "relative", width: 112, height: 112, flexShrink: 0 }}>
          <svg width="112" height="112" viewBox="0 0 112 112">
            <defs>
              <linearGradient id="verdict-ring" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#17b894" />
                <stop offset="100%" stopColor="#45efc9" />
              </linearGradient>
            </defs>
            <circle cx="56" cy="56" r={R} fill="none" stroke="rgba(150,210,200,0.08)" strokeWidth="8" />
            <motion.circle
              cx="56" cy="56" r={R} fill="none"
              stroke={useSignalRing ? "url(#verdict-ring)" : ringColor}
              strokeWidth="8" strokeLinecap="round"
              strokeDasharray={C}
              initial={{ strokeDashoffset: C }}
              animate={{ strokeDashoffset: C * (1 - score / 100) }}
              transition={{ duration: 0.6, ease: EASE, delay: 0.1 }}
              transform="rotate(-90 56 56)"
            />
          </svg>
          <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
            <span className="font-mono" style={{ fontSize: 30, fontWeight: 700, color: ringColor, lineHeight: 1 }}>{shownScore}</span>
            <span className="font-mono ds-text-muted" style={{ fontSize: 11 }}>/ 100</span>
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
        </div>

        {/* The single primary action. */}
        <motion.div {...rise(0.18)} style={{ flexShrink: 0 }}>
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
