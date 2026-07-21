"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { LinkResult } from "@/types";

interface HealthScoreProps {
  results: LinkResult[];
}

function calcScore(results: LinkResult[]): number {
  if (results.length === 0) return 100;
  const total = results.length;
  const okCount = results.filter((r) => r.label === "ok").length;
  const brokenCount = results.filter((r) => r.label === "broken").length;
  const deadCtaCount = results.filter((r) => r.label === "dead_cta").length;
  const timeoutCount = results.filter((r) => r.label === "timeout").length;

  let score = Math.round((okCount / total) * 100);
  score -= brokenCount * 3;
  score -= deadCtaCount * 2;
  score -= timeoutCount * 1;
  return Math.max(0, Math.min(100, score));
}

function scoreColor(score: number): string {
  if (score >= 90) return "#4caf7d";
  if (score >= 70) return "#f5a623";
  return "#e05c5c";
}

function scoreHeadline(score: number): string {
  if (score >= 90) return "Your site looks great! 🎉";
  if (score >= 70) return "A few things to fix";
  return "Needs attention";
}

export default function HealthScore({ results }: HealthScoreProps) {
  const [animScore, setAnimScore] = useState(0);
  const finalScore = calcScore(results);
  const total = results.length;
  const okCount = results.filter((r) => r.label === "ok").length;
  const brokenCount = results.filter((r) => r.label === "broken").length;
  const deadCtaCount = results.filter((r) => r.label === "dead_cta").length;
  const redirectCount = results.filter((r) => r.label === "redirect").length;
  const blockedCount = results.filter(
    (r) => r.label === "blocked" || r.label === "forbidden"
  ).length;

  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const start = performance.now();
    const duration = 1200;
    function animate(now: number) {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setAnimScore(Math.round(eased * finalScore));
      if (t < 1) rafRef.current = requestAnimationFrame(animate);
    }
    rafRef.current = requestAnimationFrame(animate);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [finalScore]);

  const size = 140;
  const strokeWidth = 10;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference - (animScore / 100) * circumference;
  const color = scoreColor(finalScore);
  const headline = scoreHeadline(finalScore);

  const breakdownItems: { icon: string; label: string; count: number }[] = [
    { icon: "✓", label: "links working fine", count: okCount },
    { icon: "✕", label: "pages no longer exist", count: brokenCount },
    { icon: "⚠", label: "buttons go nowhere", count: deadCtaCount },
    { icon: "→", label: "links redirect somewhere else", count: redirectCount },
    { icon: "?", label: "links we couldn't verify", count: blockedCount },
  ].filter((item) => item.count > 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="w-full max-w-5xl mx-auto mt-8 px-4"
    >
      <div
        className="glass-card p-6 flex flex-col sm:flex-row items-center gap-8"
      >
        {/* Left — circular ring */}
        <div className="flex flex-col items-center shrink-0" style={{ width: "40%" }}>
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
            {/* Track */}
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke="var(--color-border-soft)"
              strokeWidth={strokeWidth}
            />
            {/* Progress */}
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={color}
              strokeWidth={strokeWidth}
              strokeDasharray={circumference}
              strokeDashoffset={dashOffset}
              strokeLinecap="round"
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
              style={{ transition: "stroke-dashoffset 0.05s linear" }}
            />
            {/* Score number */}
            <text
              x={size / 2}
              y={size / 2 - 6}
              textAnchor="middle"
              dominantBaseline="middle"
              fill={color}
              fontSize="28"
              fontWeight="700"
              fontFamily="var(--font-sans)"
            >
              {animScore}
            </text>
            {/* Label */}
            <text
              x={size / 2}
              y={size / 2 + 20}
              textAnchor="middle"
              dominantBaseline="middle"
              fill="var(--color-text-muted)"
              fontSize="11"
              fontWeight="400"
              fontFamily="var(--font-sans)"
            >
              Site Health
            </text>
          </svg>
        </div>

        {/* Right — summary */}
        <div className="flex flex-col gap-3" style={{ width: "60%" }}>
          <h2
            className="text-text-primary"
            style={{ fontWeight: 700, fontSize: "22px", lineHeight: 1.2 }}
          >
            {headline}
          </h2>
          <p
            className="text-text-secondary"
            style={{ fontSize: "14px" }}
          >
            We checked{" "}
            <span className="text-text-primary" style={{ fontWeight: 600 }}>{total}</span>{" "}
            links across your page. Here&apos;s what we found:
          </p>
          <ul className="flex flex-col gap-1.5">
            {breakdownItems.map((item) => (
              <li
                key={item.label}
                className="flex items-center gap-2 text-text-secondary"
                style={{ fontSize: "13px" }}
              >
                <span
                  className="text-text-muted"
                  style={{ width: 20, textAlign: "center", fontWeight: 600 }}
                >
                  {item.icon}
                </span>
                <span className="text-text-primary" style={{ fontWeight: 600 }}>
                  {item.count}
                </span>
                &nbsp;{item.label}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </motion.div>
  );
}
