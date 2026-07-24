"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { LinkResult, ScanDiff } from "@/types";
import { bucketOf, countBuckets } from "@/lib/buckets";

interface StatsBarProps {
  results: LinkResult[];
  diff?: ScanDiff | null;
}

function useCountUp(target: number, delay: number = 0): number {
  const [count, setCount] = useState(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    setCount(0);
    const timer = setTimeout(() => {
      const start = performance.now();
      const duration = 800;
      function animate(now: number) {
        const t = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - t, 3);
        setCount(Math.round(eased * target));
        if (t < 1) rafRef.current = requestAnimationFrame(animate);
      }
      rafRef.current = requestAnimationFrame(animate);
    }, delay);

    return () => {
      clearTimeout(timer);
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [target, delay]);

  return count;
}

interface StatCard {
  label: string;
  rawValue: number;
  color: string;
  bg: string;
  delay: number;
  /** Renders verbatim instead of counting up — used for "n/a" on a first scan. */
  displayValue?: string;
  hint?: string;
  /** First tile of a group — draws a heavier rule to its left. */
  groupStart?: boolean;
}

export default function StatsBar({ results, diff }: StatsBarProps) {
  const totalLinks = results.length;
  // A link can be HTTP-ok yet unverifiable (e.g. its #section may be rendered by
  // JavaScript on the target page). Such a row belongs in Unverifiable only.
  const working = results.filter((r) => r.label === "ok" && bucketOf(r) === "ok").length;
  const redirects = results.filter((r) => r.label === "redirect").length;

  // Counted by bucket, not label: a low-confidence dead-CTA candidate is
  // "unverifiable", and must not be reported to a client as a dead button.
  const { broken, dead_cta: deadCta, unverifiable: cantVerify } = countBuckets(results);

  const hasBaseline = diff?.has_baseline === true;
  // "No previous scan" is a lie when the baseline lookup failed. Say which.
  const baselineUnavailable = diff?.baseline_status === "unavailable";
  const noBaselineHint = baselineUnavailable
    ? "Couldn't load the previous scan — baseline tracking isn't set up"
    : "No previous scan to compare against";

  const stats: StatCard[] = [
    {
      label: "Total Links",
      rawValue: totalLinks,
      color: "var(--text-primary)",
      bg: "rgba(28,28,46,0.04)",
      delay: 0,
    },
    {
      label: "Working",
      rawValue: working,
      color: "#4caf7d",
      bg: "rgba(76,175,125,0.10)",
      delay: 100,
    },
    {
      label: "Broken",
      rawValue: broken,
      color: "#e05c5c",
      bg: "rgba(224,92,92,0.10)",
      delay: 200,
    },
    ...(deadCta > 0
      ? [
          {
            label: "Dead CTAs",
            rawValue: deadCta,
            color: "#f5a623",
            bg: "rgba(245,166,35,0.10)",
            delay: 300,
          },
        ]
      : []),
    {
      label: "Redirects",
      rawValue: redirects,
      color: "#4f46e5",
      bg: "rgba(79,70,229,0.10)",
      delay: 400,
    },
    // Timeouts and bot-blocked responses both live here now — they are things
    // we could not verify, not things we proved were broken.
    ...(cantVerify > 0
      ? [
          {
            label: "Unverifiable",
            rawValue: cantVerify,
            color: "#f5a623",
            bg: "rgba(245,166,35,0.10)",
            delay: 500,
          },
        ]
      : []),
    // Baseline diff. On a site's first scan there is nothing to compare
    // against, so these read "n/a" rather than a misleading 0.
    {
      label: "New Links",
      rawValue: diff?.new_links ?? 0,
      displayValue: hasBaseline && diff?.new_links != null ? undefined : "n/a",
      hint: hasBaseline ? undefined : noBaselineHint,
      color: "#7a7a8c",
      bg: "rgba(122,122,140,0.10)",
      delay: 600,
      // Everything from here on is a diff count, not an absolute count of what
      // is on the page — a heavier rule splits the bar into those two groups.
      groupStart: true,
    },
    {
      label: "New Issues",
      rawValue: diff?.new ?? 0,
      displayValue: hasBaseline ? undefined : "n/a",
      hint: hasBaseline
        ? `${diff?.fixed ?? 0} fixed · ${diff?.recurring ?? 0} still open`
        : noBaselineHint,
      color: (diff?.new ?? 0) > 0 ? "#e05c5c" : "#4caf7d",
      bg: (diff?.new ?? 0) > 0 ? "rgba(224,92,92,0.10)" : "rgba(76,175,125,0.10)",
      delay: 700,
    },
  ];

  // Mobile packs into 2 columns so the 11px labels stay legible; from sm: up it
  // is one row of stats.length. Literal class strings so Tailwind keeps them.
  const smCols =
    stats.length >= 8 ? "sm:grid-cols-8" : stats.length === 7 ? "sm:grid-cols-7" : "sm:grid-cols-6";

  return (
    <div className="w-full">
      {/* One joined bar. gap 0 at every breakpoint; the hairline dividers come
          from each tile's right/bottom box-shadow, clipped to the rounded
          container by overflow-hidden — so when the grid wraps to 2 columns on
          mobile they read as row + column dividers, never gaps. Rounded corners
          live on the outer container only. */}
      <div
        className={`grid grid-cols-2 ${smCols} overflow-hidden`}
        style={{ gap: 0 }}
      >
        {stats.map((stat) => (
          <StatCardItem key={stat.label} stat={stat} />
        ))}
      </div>
    </div>
  );
}

function StatCardItem({ stat }: { stat: StatCard }) {
  const animValue = useCountUp(stat.rawValue, stat.delay);
  const isPlaceholder = stat.displayValue !== undefined;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: stat.delay / 1000, duration: 0.4 }}
      className="p-5 text-center"
      // Right + bottom hairlines = dividers between tiles (columns always, rows
      // once wrapped on mobile). The outer edges' shadows are clipped by the
      // container's overflow-hidden, so no double border.
      style={{
        background: stat.bg,
        boxShadow: [
          "1px 0 0 var(--border-subtle)",
          "0 1px 0 var(--border-subtle)",
          // Group boundary: a heavier inset rule on the left (inset so it adds
          // no layout shift and stays clipped to the bar's rounded corners).
          ...(stat.groupStart ? ["inset 2px 0 0 var(--border-strong)"] : []),
        ].join(", "),
      }}
      title={stat.hint}
    >
      <div
        className="text-[11px] uppercase tracking-widest mb-2"
        style={{
          fontFamily: "var(--font-poppins), Poppins, sans-serif",
          fontWeight: 300,
          color: "var(--text-muted)",
        }}
      >
        {stat.label}
      </div>
      <div
        className="text-4xl tabular-nums"
        style={{
          fontFamily: "var(--font-poppins), Poppins, sans-serif",
          fontWeight: 700,
          color: isPlaceholder ? "var(--text-muted)" : stat.color,
        }}
      >
        {isPlaceholder ? stat.displayValue : animValue}
      </div>
      {stat.hint && (
        <div
          className="text-[10px] mt-1.5"
          style={{ color: "var(--text-muted)" }}
        >
          {stat.hint}
        </div>
      )}
    </motion.div>
  );
}
