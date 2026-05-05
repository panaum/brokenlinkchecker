"use client";

import { motion } from "framer-motion";
import { LinkResult } from "@/types";
import {
  XCircle,
  MousePointerClick,
  ArrowRight,
  Shield,
  CheckCircle2,
} from "lucide-react";

interface SummaryBannerProps {
  results: LinkResult[];
}

export default function SummaryBanner({ results }: SummaryBannerProps) {
  const brokenCount = results.filter((r) => r.label === "broken").length;
  const deadCtaCount = results.filter((r) => r.label === "dead_cta").length;
  const redirectCount = results.filter((r) => r.label === "redirect").length;
  const blockedCount = results.filter(
    (r) => r.label === "blocked" || r.label === "forbidden"
  ).length;

  type Card = {
    id: string;
    icon: React.ReactNode;
    title: string;
    subtitle: string;
    borderColor: string;
    badge?: string;
    badgeColor?: string;
  };

  const cards: Card[] = [];

  if (brokenCount > 0) {
    cards.push({
      id: "broken",
      icon: <XCircle size={20} color="#f87171" />,
      title: `${brokenCount} broken link${brokenCount !== 1 ? "s" : ""} found`,
      subtitle: "These pages no longer exist and should be fixed immediately",
      borderColor: "#f87171",
      badge: "High Priority",
      badgeColor: "#f87171",
    });
  }

  if (deadCtaCount > 0) {
    cards.push({
      id: "dead_cta",
      icon: <MousePointerClick size={20} color="#fbbf24" />,
      title: `${deadCtaCount} button${deadCtaCount !== 1 ? "s" : ""} go nowhere`,
      subtitle: "Visitors clicking these will be confused or frustrated",
      borderColor: "#fbbf24",
      badge: "Fix Soon",
      badgeColor: "#fbbf24",
    });
  }

  if (redirectCount > 0) {
    cards.push({
      id: "redirect",
      icon: <ArrowRight size={20} color="#fb923c" />,
      title: `${redirectCount} link${redirectCount !== 1 ? "s" : ""} are redirecting`,
      subtitle:
        "These work but slow down your page — update them to point directly to the final URL",
      borderColor: "#fb923c",
      badge: "Low Priority",
      badgeColor: "#fb923c",
    });
  }

  if (blockedCount > 0) {
    cards.push({
      id: "blocked",
      icon: <Shield size={20} color="#e879f9" />,
      title: `${blockedCount} link${blockedCount !== 1 ? "s" : ""} couldn't be verified`,
      subtitle:
        "Probably fine — these sites block automated checkers like LinkedIn",
      borderColor: "#e879f9",
    });
  }

  if (brokenCount === 0 && deadCtaCount === 0) {
    cards.push({
      id: "all_clear",
      icon: <CheckCircle2 size={20} color="#4ade80" />,
      title: "No broken links found!",
      subtitle: "Every link on this page is working",
      borderColor: "#4ade80",
    });
  }

  if (cards.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.15 }}
      className="w-full max-w-5xl mx-auto mt-5 px-4"
    >
      <div className="flex flex-col sm:flex-row gap-3 overflow-x-auto pb-1">
        {cards.map((card, i) => (
          <motion.div
            key={card.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 + i * 0.08 }}
            className="glass-card p-4 flex flex-col gap-2 flex-1 min-w-[220px]"
            style={{
              borderLeft: `3px solid ${card.borderColor}`,
            }}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                {card.icon}
                <span
                  style={{
                    fontFamily: "var(--font-poppins), Poppins, sans-serif",
                    fontWeight: 600,
                    fontSize: "14px",
                    color: "#fff",
                  }}
                >
                  {card.title}
                </span>
              </div>
              {card.badge && (
                <span
                  className="shrink-0 text-xs px-2 py-0.5 rounded-full"
                  style={{
                    fontFamily: "var(--font-poppins), Poppins, sans-serif",
                    fontWeight: 500,
                    fontSize: "11px",
                    color: card.badgeColor,
                    background: `${card.badgeColor}18`,
                    border: `1px solid ${card.badgeColor}33`,
                  }}
                >
                  {card.badge}
                </span>
              )}
            </div>
            <p
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontWeight: 400,
                fontSize: "12px",
                color: "rgba(255,255,255,0.55)",
                lineHeight: 1.5,
              }}
            >
              {card.subtitle}
            </p>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}
