"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { LinkResult } from "@/types";
import { bucketOf, countBuckets } from "@/lib/buckets";

interface StatsBarProps {
  results: LinkResult[];
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
}

export default function StatsBar({ results }: StatsBarProps) {
  const totalLinks = results.length;
  // A link can be HTTP-ok yet unverifiable (e.g. its #section may be rendered by
  // JavaScript on the target page). Such a row belongs in Unverifiable only.
  const working = results.filter((r) => r.label === "ok" && bucketOf(r) === "ok").length;
  const redirects = results.filter((r) => r.label === "redirect").length;

  // Counted by bucket, not label: a low-confidence dead-CTA candidate is
  // "unverifiable", and must not be reported to a client as a dead button.
  const { broken, dead_cta: deadCta, unverifiable: cantVerify } = countBuckets(results);

  const stats: StatCard[] = [
    {
      label: "Total Links",
      rawValue: totalLinks,
      color: "#ffffff",
      bg: "rgba(255,255,255,0.08)",
      delay: 0,
    },
    {
      label: "Working",
      rawValue: working,
      color: "#4ade80",
      bg: "rgba(74,222,128,0.10)",
      delay: 100,
    },
    {
      label: "Broken",
      rawValue: broken,
      color: "#f87171",
      bg: "rgba(248,113,113,0.10)",
      delay: 200,
    },
    ...(deadCta > 0
      ? [
          {
            label: "Dead CTAs",
            rawValue: deadCta,
            color: "#fb923c",
            bg: "rgba(251,146,60,0.10)",
            delay: 300,
          },
        ]
      : []),
    {
      label: "Redirects",
      rawValue: redirects,
      color: "#e879f9",
      bg: "rgba(232,121,249,0.10)",
      delay: 400,
    },
    // Timeouts and bot-blocked responses both live here now — they are things
    // we could not verify, not things we proved were broken.
    ...(cantVerify > 0
      ? [
          {
            label: "Unverifiable",
            rawValue: cantVerify,
            color: "#fbbf24",
            bg: "rgba(251,191,36,0.10)",
            delay: 500,
          },
        ]
      : []),
  ];

  return (
    <div className="w-full max-w-5xl mx-auto mt-8 px-4">
      <div
        className={`grid gap-4`}
        style={{
          gridTemplateColumns: `repeat(${Math.min(stats.length, 4)}, minmax(0, 1fr))`,
        }}
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

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: stat.delay / 1000, duration: 0.4 }}
      className="glass-card p-5 text-center"
      style={{ background: stat.bg }}
    >
      <div
        className="text-[11px] uppercase tracking-widest mb-2"
        style={{
          fontFamily: "var(--font-poppins), Poppins, sans-serif",
          fontWeight: 300,
          color: "rgba(255,255,255,0.5)",
        }}
      >
        {stat.label}
      </div>
      <div
        className="text-4xl tabular-nums"
        style={{
          fontFamily: "var(--font-poppins), Poppins, sans-serif",
          fontWeight: 700,
          color: stat.color,
        }}
      >
        {animValue}
      </div>
    </motion.div>
  );
}
