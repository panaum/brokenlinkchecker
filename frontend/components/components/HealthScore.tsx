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
  if (score >= 90) return "#4ade80";
  if (score >= 70) return "#fb923c";
  return "#f87171";
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
            <defs>
              <linearGradient id="ringGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="rgb(65,0,153)" />
                <stop offset="100%" stopColor="rgb(138,26,155)" />
              </linearGradient>
            </defs>
            {/* Track */}
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke="rgba(255,255,255,0.08)"
              strokeWidth={strokeWidth}
            />
            {/* Progress */}
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke="url(#ringGradient)"
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
              fontFamily="Poppins, sans-serif"
            >
              {animScore}
            </text>
            {/* Label */}
            <text
              x={size / 2}
              y={size / 2 + 20}
              textAnchor="middle"
              dominantBaseline="middle"
              fill="rgba(255,255,255,0.5)"
              fontSize="11"
              fontWeight="400"
              fontFamily="Poppins, sans-serif"
            >
              Site Health
            </text>
          </svg>
        </div>

        {/* Right — summary */}
        <div className="flex flex-col gap-3" style={{ width: "60%" }}>
          <h2
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontWeight: 700,
              fontSize: "22px",
              color: "#fff",
              lineHeight: 1.2,
            }}
          >
            {headline}
          </h2>
          <p
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontWeight: 400,
              fontSize: "14px",
              color: "rgba(255,255,255,0.55)",
            }}
          >
            We checked{" "}
            <span style={{ color: "#fff", fontWeight: 600 }}>{total}</span>{" "}
            links across your page. Here&apos;s what we found:
          </p>
          <ul className="flex flex-col gap-1.5">
            {breakdownItems.map((item) => (
              <li
                key={item.label}
                className="flex items-center gap-2"
                style={{
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                  fontSize: "13px",
                  color: "rgba(255,255,255,0.7)",
                }}
              >
                <span
                  style={{
                    width: 20,
                    textAlign: "center",
                    color: "rgba(255,255,255,0.4)",
                    fontWeight: 600,
                  }}
                >
                  {item.icon}
                </span>
                <span style={{ fontWeight: 600, color: "#fff" }}>
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
