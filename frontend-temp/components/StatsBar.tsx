"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { LinkResult } from "@/types";

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
  const working = results.filter((r) => r.label === "ok").length;
  const broken = results.filter((r) => r.label === "broken").length;
  const deadCta = results.filter((r) => r.label === "dead_cta").length;
  const redirects = results.filter((r) => r.label === "redirect").length;
  const cantVerify = results.filter(
    (r) => r.label === "blocked" || r.label === "forbidden"
  ).length;
  const timeouts = results.filter(
    (r) => r.label === "timeout" || r.label === "error"
  ).length;

  const stats: StatCard[] = [
    {
      label: "Total Links",
      rawValue: totalLinks,
      color: "#1c1c2e",
      bg: "#ffffff",
      delay: 0,
    },
    {
      label: "Working",
      rawValue: working,
      color: "#4caf7d",
      bg: "rgba(76,175,125,0.08)",
      delay: 100,
    },
    {
      label: "Broken",
      rawValue: broken,
      color: "#e05c5c",
      bg: "rgba(224,92,92,0.08)",
      delay: 200,
    },
    ...(deadCta > 0
      ? [
          {
            label: "Dead Buttons",
            rawValue: deadCta,
            color: "#f5a623",
            bg: "rgba(245,166,35,0.08)",
            delay: 300,
          },
        ]
      : []),
    {
      label: "Redirects",
      rawValue: redirects,
      color: "#f5a623",
      bg: "rgba(245,166,35,0.08)",
      delay: 400,
    },
    ...(cantVerify > 0
      ? [
          {
            label: "Can't Verify",
            rawValue: cantVerify,
            color: "#4f46e5",
            bg: "rgba(79,70,229,0.07)",
            delay: 500,
          },
        ]
      : []),
    ...(timeouts > 0
      ? [
          {
            label: "Timeouts",
            rawValue: timeouts,
            color: "#66667a",
            bg: "rgba(102,102,122,0.07)",
            delay: 600,
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
        className="text-[11px] uppercase tracking-widest mb-2 text-text-muted"
        style={{ fontWeight: 500 }}
      >
        {stat.label}
      </div>
      <div
        className="text-4xl tabular-nums"
        style={{ fontWeight: 700, color: stat.color }}
      >
        {animValue}
      </div>
    </motion.div>
  );
}
