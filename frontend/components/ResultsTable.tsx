"use client";

import { useState, useMemo, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ExternalLink,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  Ghost,
  AlertCircle,
  Clock,
  Zap,
} from "lucide-react";
import { LinkResult, SortOption } from "@/types";
import StatusPill from "./StatusPill";
import { latencyColor } from "@/lib/format";
import ExportButton from "./ExportButton";
import SuggestionCard from "./SuggestionCard";
import RedirectDownloadButton from "./RedirectDownload";
import RedirectMap from "./RedirectMap";

interface ResultsTableProps {
  results: LinkResult[];
  sortOption: SortOption;
  scannedUrl?: string;
  healthScore?: number;
  onScrollToHistory?: () => void;
}

// ─── Zone config ─────────────────────────────────────────────────────────────
const ZONE_ORDER = [
  "Form",
  "Navigation",
  "Header",
  "CTA",
  "Body text",
  "Footer",
  "Other",
  "Dead CTA",
];

const ZONE_DOT_COLORS: Record<string, string> = {
  // A broken form is the most expensive defect on a lead-gen site.
  Form: "#f472b6",
  Navigation: "#60a5fa",
  Header: "#7c6cff",
  Footer: "#94a3b8",
  CTA: "#fbbf24",
  "Body text": "#e2e8f0",
  Other: "#64748b",
  "Dead CTA": "#f87171",
};

// ─── Uptime helper ────────────────────────────────────────────────────────────
function getDaysBroken(firstSeenAt: string): number {
  const first = new Date(firstSeenAt);
  const now = new Date();
  return Math.floor((now.getTime() - first.getTime()) / (1000 * 60 * 60 * 24));
}

// ─── Impact factor labels ─────────────────────────────────────────────────────
const ZONE_WEIGHTS: Record<string, number> = {
  CTA: 40, Navigation: 30, Header: 25, "Body text": 15, Footer: 10, Other: 5, "Dead CTA": 35,
};

// ─── Row status styling ───────────────────────────────────────────────────────
const ROW_ACCENT: Record<
  string,
  { border: string; bg: string } | undefined
> = {
  broken: { border: "#f87171", bg: "rgba(248,113,113,0.04)" },
  error: { border: "#f87171", bg: "rgba(248,113,113,0.04)" },
  dead_cta: { border: "#fbbf24", bg: "rgba(251,191,36,0.03)" },
  redirect: { border: "#fb923c", bg: "rgba(251,146,60,0.03)" },
};

// ─── Sort weights ─────────────────────────────────────────────────────────────
const LABEL_WEIGHT: Record<string, number> = {
  broken: 0,
  dead_cta: 1,
  redirect: 2,
  blocked: 3,
  forbidden: 3,
  timeout: 4,
  error: 5,
  ok: 6,
};

// ─── Impact detail card for expanded rows ─────────────────────────────────────
function ImpactDetailCard({
  impact,
  category,
  label,
  daysBroken,
}: {
  impact: { score: number; level: string; color: string; description: string };
  category: string;
  label: string;
  daysBroken: number;
}) {
  const [showWhy, setShowWhy] = useState(false);

  const zoneScore = ZONE_WEIGHTS[category] ?? 5;
  let timeScore = 5;
  if (daysBroken > 14) timeScore = 30;
  else if (daysBroken > 7) timeScore = 20;
  else if (daysBroken > 3) timeScore = 15;
  else if (daysBroken > 1) timeScore = 10;

  let severityScore = 20;
  let severityLabel = "Error";
  if (label === "broken") { severityScore = 30; severityLabel = "Broken link"; }
  else if (label === "dead_cta") { severityScore = 25; severityLabel = "Dead CTA"; }

  return (
    <div
      className="rounded-xl px-4 py-3 mt-1"
      style={{
        background: "rgba(255,255,255,0.03)",
        border: `1px solid ${impact.color}22`,
      }}
    >
      <div className="flex items-center gap-3 mb-2">
        <Zap size={14} style={{ color: impact.color }} />
        <span
          style={{
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
            fontSize: "13px",
            fontWeight: 600,
            color: impact.color,
          }}
        >
          {impact.level} Impact
        </span>
        <span
          style={{
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
            fontSize: "12px",
            fontWeight: 400,
            color: "rgba(255,255,255,0.4)",
          }}
        >
          {impact.score}/100
        </span>
      </div>
      <p
        style={{
          fontFamily: "var(--font-poppins), Poppins, sans-serif",
          fontSize: "12px",
          color: "rgba(255,255,255,0.5)",
          margin: 0,
          marginBottom: 6,
        }}
      >
        {impact.description}
      </p>
      <button
        onClick={(e) => { e.stopPropagation(); setShowWhy(!showWhy); }}
        className="cursor-pointer"
        style={{
          background: "none",
          border: "none",
          padding: 0,
          fontFamily: "var(--font-poppins), Poppins, sans-serif",
          fontSize: "11px",
          fontWeight: 500,
          color: "rgba(255,255,255,0.3)",
          textDecoration: "underline",
          textDecorationStyle: "dotted" as const,
          textUnderlineOffset: "3px",
        }}
      >
        {showWhy ? "Hide breakdown" : "Why this score?"}
      </button>
      {showWhy && (
        <div className="mt-2 flex flex-col gap-1">
          {[
            { label: `Zone: ${category}`, value: `+${zoneScore}`, color: "#60a5fa" },
            { label: `Time broken: ${daysBroken} days`, value: `+${timeScore}`, color: "#fbbf24" },
            { label: `Severity: ${severityLabel}`, value: `+${severityScore}`, color: "#f87171" },
          ].map((f) => (
            <div key={f.label} className="flex items-center justify-between">
              <span
                style={{
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                  fontSize: "11px",
                  color: "rgba(255,255,255,0.4)",
                }}
              >
                {f.label}
              </span>
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: "11px",
                  fontWeight: 600,
                  color: f.color,
                }}
              >
                {f.value}
              </span>
            </div>
          ))}
          <div
            className="flex items-center justify-between mt-1 pt-1"
            style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}
          >
            <span
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontSize: "11px",
                fontWeight: 600,
                color: "rgba(255,255,255,0.6)",
              }}
            >
              Total
            </span>
            <span
              style={{
                fontFamily: "monospace",
                fontSize: "11px",
                fontWeight: 700,
                color: impact.color,
              }}
            >
              {impact.score}/100 → {impact.level}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Expandable row detail ────────────────────────────────────────────────────
function RowDetail({ result }: { result: LinkResult }) {
  const [copied, setCopied] = useState(false);

  const doCopy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  let basicSuggestion: string | null = null;
  if ((result.label === "broken" || result.label === "error") && !result.suggestion) {
    basicSuggestion = "Remove this link or replace it with a working URL.";
  } else if (result.label === "redirect" && result.final_url) {
    basicSuggestion = `Update your link to point here instead: ${result.final_url}`;
  } else if (result.label === "dead_cta") {
    basicSuggestion = "Add a destination URL to this button.";
  }

  return (
    <motion.tr
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
    >
      <td
        colSpan={6}
        style={{ padding: 0, borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <div
          style={{
            padding: "14px 20px 14px 36px",
            background: "rgba(255,255,255,0.025)",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          {/* Full URL + copy */}
          <div className="flex items-center gap-2 flex-wrap">
            <span
              style={{
                fontFamily: "monospace",
                fontSize: "12px",
                color: "rgba(255,255,255,0.55)",
                wordBreak: "break-all",
              }}
            >
              {result.url}
            </span>
            <button
              onClick={() => doCopy(result.url)}
              className="shrink-0 cursor-pointer transition-colors"
              title="Copy URL"
            >
              {copied ? (
                <Check size={13} style={{ color: "#4ade80" }} />
              ) : (
                <Copy size={13} style={{ color: "rgba(255,255,255,0.3)" }} />
              )}
            </button>
            <a
              href={result.url}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 transition-opacity hover:opacity-80"
            >
              <ExternalLink size={13} style={{ color: "rgba(255,255,255,0.3)" }} />
            </a>
          </div>

          {/* Redirect route map when there's a chain; else the plain final URL. */}
          {result.redirect_chain && result.redirect_chain.length > 0 ? (
            <RedirectMap result={result} />
          ) : result.final_url && result.final_url !== result.url ? (
            <div className="flex items-center gap-2">
              <span
                style={{
                  fontSize: "11px",
                  color: "rgba(255,255,255,0.35)",
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                }}
              >
                Final destination:
              </span>
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: "12px",
                  color: "#fb923c",
                  wordBreak: "break-all",
                }}
              >
                {result.final_url}
              </span>
            </div>
          ) : null}

          {/* Meta row */}
          <div className="flex flex-wrap gap-4">
            {result.status_code && (
              <span
                style={{
                  fontSize: "11px",
                  color: "rgba(255,255,255,0.3)",
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                }}
              >
                HTTP {result.status_code}
              </span>
            )}
            {result.source_element && (
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: "11px",
                  color: "rgba(255,255,255,0.25)",
                }}
              >
                {result.source_element}
              </span>
            )}
            <span
              style={{
                fontSize: "11px",
                color: "rgba(255,255,255,0.3)",
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
              }}
            >
              {result.response_ms}ms
            </span>
          </div>

          {/* Uptime indicator */}
          {result.first_seen_at && (result.label === "broken" || result.label === "dead_cta" || result.label === "error") && (
            <div className="flex items-center gap-2">
              <span
                style={{
                  fontSize: "11px",
                  color: "rgba(255,255,255,0.4)",
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                }}
              >
                Broken for: {getDaysBroken(result.first_seen_at)} days
              </span>
              {getDaysBroken(result.first_seen_at) > 7 && (
                <span style={{ color: "#f87171", fontSize: "11px" }}>⚠️ Long-standing issue</span>
              )}
            </div>
          )}

          {/* Found on pages list */}
          {result.found_on_pages && result.found_on_pages.length > 0 && (
            <div className="flex flex-col gap-1 mt-1">
              <span
                style={{
                  fontSize: "11px",
                  color: "rgba(255,255,255,0.35)",
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                }}
              >
                Found on {result.found_on_pages.length} page{result.found_on_pages.length !== 1 ? "s" : ""}:
              </span>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {result.found_on_pages.map((p, idx) => (
                  <span
                    key={idx}
                    style={{
                      fontFamily: "monospace",
                      fontSize: "11px",
                      color: "#7c6cff",
                      background: "rgba(167,139,250,0.1)",
                      border: "1px solid rgba(167,139,250,0.15)",
                      borderRadius: "4px",
                      padding: "2px 6px",
                    }}
                  >
                    {p}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Business Impact Card */}
          {result.impact && (
            <ImpactDetailCard
              impact={result.impact}
              category={result.category}
              label={result.label}
              daysBroken={result.first_seen_at ? getDaysBroken(result.first_seen_at) : 0}
            />
          )}

          {/* AI Suggestion Card (Upgrade 3) */}
          {result.suggestion && (
            <SuggestionCard suggestion={result.suggestion} />
          )}

          {/* Basic suggestion fallback */}
          {basicSuggestion && !result.suggestion && (
            <div
              className="flex items-start gap-2 mt-1 rounded-lg px-3 py-2"
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.07)",
              }}
            >
              <AlertCircle size={13} style={{ color: "#fbbf24", marginTop: 2, flexShrink: 0 }} />
              <span
                style={{
                  fontSize: "12px",
                  color: "rgba(255,255,255,0.6)",
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                  lineHeight: 1.5,
                }}
              >
                {basicSuggestion}
              </span>
            </div>
          )}
        </div>
      </td>
    </motion.tr>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function ResultsTable({
  results,
  sortOption,
  scannedUrl = "",
  healthScore = 0,
  onScrollToHistory,
}: ResultsTableProps) {
  const [copiedUrl, setCopiedUrl] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [showToast, setShowToast] = useState(false);
  const [toastTimeout, setToastTimeout] = useState<ReturnType<typeof setTimeout> | null>(null);

  const handleCopy = useCallback(
    async (url: string) => {
      await navigator.clipboard.writeText(url);
      setCopiedUrl(url);
      setShowToast(true);
      if (toastTimeout) clearTimeout(toastTimeout);
      const t = setTimeout(() => {
        setCopiedUrl(null);
        setShowToast(false);
      }, 1500);
      setToastTimeout(t);
    },
    [toastTimeout]
  );

  const toggleRow = useCallback((key: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }, []);

  const toggleGroup = useCallback((zone: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      next.has(zone) ? next.delete(zone) : next.add(zone);
      return next;
    });
  }, []);

  // Sort results based on sortOption
  const sortedResults = useMemo(() => {
    return [...results].sort((a, b) => {
      if (sortOption === "status") {
        const wa = LABEL_WEIGHT[a.label] ?? 99;
        const wb = LABEL_WEIGHT[b.label] ?? 99;
        return wa !== wb ? wa - wb : a.url.localeCompare(b.url);
      }
      if (sortOption === "zone") {
        const za = ZONE_ORDER.indexOf(a.category);
        const zb = ZONE_ORDER.indexOf(b.category);
        return za !== zb ? za - zb : a.url.localeCompare(b.url);
      }
      if (sortOption === "response_ms") {
        return b.response_ms - a.response_ms;
      }
      return 0;
    });
  }, [results, sortOption]);

  // Group by zone
  const groups = useMemo(() => {
    const map = new Map<string, LinkResult[]>();
    ZONE_ORDER.forEach((z) => map.set(z, []));

    for (const r of sortedResults) {
      const zone = r.category in Object.fromEntries(map) ? r.category : "Other";
      const existing = map.get(zone);
      if (existing) {
        existing.push(r);
      } else {
        map.set(zone, [r]);
      }
    }

    // default collapse groups with no issues
    const result: { zone: string; items: LinkResult[] }[] = [];
    map.forEach((items, zone) => {
      if (items.length > 0) {
        result.push({ zone, items });
      }
    });
    return result;
  }, [sortedResults]);

  // Auto-collapse groups with all-ok links on first load
  useMemo(() => {
    const toCollapse = new Set<string>();
    groups.forEach(({ zone, items }) => {
      const hasIssue = items.some(
        (r) => r.label !== "ok" && r.label !== "blocked" && r.label !== "forbidden"
      );
      if (!hasIssue) toCollapse.add(zone);
    });
    setCollapsedGroups(toCollapse);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [results]); // only on fresh results

  if (results.length === 0) {
    return (
      <div className="w-full max-w-5xl mx-auto mt-8 px-4">
        <div className="glass-card p-16 flex flex-col items-center justify-center text-center gap-6">
          <svg width="80" height="80" viewBox="0 0 80 80" fill="none">
            <circle cx="40" cy="40" r="36" stroke="rgba(255,255,255,0.08)" strokeWidth="2" />
            <circle cx="40" cy="40" r="24" stroke="rgba(255,255,255,0.05)" strokeWidth="2" />
            <line x1="25" y1="55" x2="55" y2="25" stroke="rgba(255,255,255,0.12)" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <div>
            <p
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontWeight: 600,
                fontSize: "18px",
                color: "rgba(255,255,255,0.6)",
                marginBottom: 6,
              }}
            >
              No links matched this filter
            </p>
            <p
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontWeight: 400,
                fontSize: "14px",
                color: "rgba(255,255,255,0.3)",
              }}
            >
              Try selecting a different filter or clearing your search
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-5xl mx-auto mt-6 px-4 relative">
      {/* Copy toast */}
      <AnimatePresence>
        {showToast && (
          <motion.div
            key="toast"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 flex items-center gap-2 px-4 py-2 rounded-full"
            style={{
              background: "rgba(20,10,40,0.95)",
              border: "1px solid rgba(74,222,128,0.3)",
              backdropFilter: "blur(12px)",
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontSize: "13px",
              fontWeight: 500,
              color: "#4ade80",
              boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
            }}
          >
            <Check size={14} />
            Copied!
          </motion.div>
        )}
      </AnimatePresence>

      <div className="glass-card overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
          <h3
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontWeight: 500,
              fontSize: "14px",
              color: "rgba(255,255,255,0.6)",
            }}
          >
            Results
          </h3>
          <div className="flex items-center gap-2">
            {onScrollToHistory && (
              <button
                onClick={onScrollToHistory}
                className="glass-card inline-flex items-center gap-2 px-4 py-2 text-white/60 hover:text-white transition-colors cursor-pointer"
                style={{
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                  fontWeight: 500,
                  fontSize: "13px",
                }}
              >
                <Clock size={14} />
                History
              </button>
            )}
            <RedirectDownloadButton results={results} />
            <ExportButton
              results={results}
              scannedUrl={scannedUrl}
              healthScore={healthScore}
            />
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px]">
            <thead>
              <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
                {["Status", "Link Text", "URL", "Where on Page", "Time", ""].map(
                  (col) => (
                    <th
                      key={col}
                      className="px-4 py-3 text-left"
                      style={{
                        fontSize: "10px",
                        textTransform: "uppercase",
                        letterSpacing: "0.08em",
                        color: "rgba(255,255,255,0.35)",
                        fontFamily: "var(--font-poppins), Poppins, sans-serif",
                        fontWeight: 500,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {col}
                    </th>
                  )
                )}
              </tr>
            </thead>

            <tbody>
              {groups.map(({ zone, items }) => {
                const isCollapsed = collapsedGroups.has(zone);
                const issueCount = items.filter(
                  (r) =>
                    r.label === "broken" ||
                    r.label === "dead_cta" ||
                    r.label === "error"
                ).length;
                const dotColor = ZONE_DOT_COLORS[zone] ?? "#64748b";

                return [
                  /* Group header row */
                  <tr
                    key={`group-${zone}`}
                    onClick={() => toggleGroup(zone)}
                    style={{
                      cursor: "pointer",
                      background: "rgba(255,255,255,0.025)",
                      borderBottom: "1px solid rgba(255,255,255,0.06)",
                      borderTop: "1px solid rgba(255,255,255,0.06)",
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLTableRowElement).style.background =
                        "rgba(255,255,255,0.04)";
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLTableRowElement).style.background =
                        "rgba(255,255,255,0.025)";
                    }}
                  >
                    <td colSpan={6} style={{ padding: "8px 16px" }}>
                      <div className="flex items-center gap-3">
                        <span
                          className="w-2 h-2 rounded-full shrink-0"
                          style={{ background: dotColor }}
                        />
                        <span
                          style={{
                            fontFamily: "var(--font-poppins), Poppins, sans-serif",
                            fontWeight: 600,
                            fontSize: "11px",
                            textTransform: "uppercase",
                            letterSpacing: "0.07em",
                            color: "rgba(255,255,255,0.55)",
                          }}
                        >
                          {zone}
                        </span>
                        <span
                          style={{
                            fontSize: "11px",
                            color: "rgba(255,255,255,0.3)",
                            fontFamily: "var(--font-poppins), Poppins, sans-serif",
                          }}
                        >
                          {items.length} link{items.length !== 1 ? "s" : ""}
                          {issueCount > 0 && (
                            <span style={{ color: "#f87171", marginLeft: 4 }}>
                              · {issueCount} broken
                            </span>
                          )}
                        </span>
                        <span className="ml-auto">
                          {isCollapsed ? (
                            <ChevronDown size={14} style={{ color: "rgba(255,255,255,0.3)" }} />
                          ) : (
                            <ChevronUp size={14} style={{ color: "rgba(255,255,255,0.3)" }} />
                          )}
                        </span>
                      </div>
                    </td>
                  </tr>,

                  /* Item rows */
                  ...(isCollapsed
                    ? []
                    : items.map((result, idx) => {
                        const rowKey = `${result.url}-${zone}-${idx}`;
                        const accent = ROW_ACCENT[result.label];
                        const isExpanded = expandedRows.has(rowKey);

                        let urlHost = "";
                        let urlPath = result.url;
                        try {
                          const u = new URL(result.url);
                          urlHost = u.hostname;
                          urlPath = u.pathname + u.search;
                        } catch {
                          // noop
                        }

                        return [
                          <motion.tr
                            key={rowKey}
                            initial={
                              idx < 20
                                ? { opacity: 0, y: 12 }
                                : { opacity: 1, y: 0 }
                            }
                            animate={{ opacity: 1, y: 0 }}
                            transition={{
                              delay: idx < 20 ? idx * 0.02 : 0,
                              duration: 0.25,
                            }}
                            onClick={() => toggleRow(rowKey)}
                            style={{
                              cursor: "pointer",
                              borderBottom: "1px solid rgba(255,255,255,0.05)",
                              borderLeft: accent
                                ? `3px solid ${accent.border}`
                                : "3px solid transparent",
                              background: isExpanded
                                ? "rgba(255,255,255,0.04)"
                                : accent
                                ? accent.bg
                                : "transparent",
                              transition: "background 0.15s",
                            }}
                            onMouseEnter={(e) => {
                              if (!isExpanded)
                                (e.currentTarget as HTMLElement).style.background =
                                  "rgba(255,255,255,0.03)";
                            }}
                            onMouseLeave={(e) => {
                              if (!isExpanded)
                                (e.currentTarget as HTMLElement).style.background =
                                  accent ? accent.bg : "transparent";
                            }}
                          >
                            {/* Status */}
                            <td style={{ padding: "10px 16px", verticalAlign: "middle" }}>
                              <StatusPill label={result.label} />
                            </td>

                            {/* Link text */}
                            <td style={{ padding: "10px 16px", verticalAlign: "middle" }}>
                              <span
                                style={{
                                  fontFamily:
                                    "var(--font-poppins), Poppins, sans-serif",
                                  fontSize: "13px",
                                  fontWeight: 400,
                                  color: "rgba(255,255,255,0.7)",
                                  display: "block",
                                  maxWidth: 160,
                                  overflow: "hidden",
                                  textOverflow: "ellipsis",
                                  whiteSpace: "nowrap",
                                }}
                                title={result.anchor_text}
                              >
                                {result.anchor_text || "—"}
                              </span>
                            </td>

                            {/* URL */}
                            <td
                              style={{
                                padding: "10px 16px",
                                verticalAlign: "middle",
                                minWidth: 220,
                              }}
                            >
                              <div className="flex flex-col">
                                {urlHost && (
                                  <span
                                    style={{
                                      fontFamily: "monospace",
                                      fontSize: "10px",
                                      color: "rgba(255,255,255,0.2)",
                                      marginBottom: 2,
                                      display: "block",
                                    }}
                                  >
                                    {urlHost}
                                  </span>
                                )}
                                <div
                                  className="flex items-center gap-1.5"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <span
                                    style={{
                                      fontFamily: "monospace",
                                      fontSize: "12px",
                                      color: "rgba(255,255,255,0.65)",
                                      maxWidth: 200,
                                      overflow: "hidden",
                                      textOverflow: "ellipsis",
                                      whiteSpace: "nowrap",
                                      display: "block",
                                    }}
                                    title={result.url}
                                  >
                                    {urlPath.length > 40
                                      ? urlPath.slice(0, 40) + "…"
                                      : urlPath}
                                  </span>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleCopy(result.url);
                                    }}
                                    className="shrink-0 cursor-pointer transition-colors"
                                  >
                                    {copiedUrl === result.url ? (
                                      <Check size={12} style={{ color: "#4ade80" }} />
                                    ) : (
                                      <Copy
                                        size={12}
                                        style={{ color: "rgba(255,255,255,0.2)" }}
                                      />
                                    )}
                                  </button>
                                </div>
                              </div>
                            </td>

                            <td style={{ padding: "10px 16px", verticalAlign: "middle" }}>
                              <div className="flex flex-col gap-1 items-start">
                                <span
                                  className="inline-flex items-center gap-1.5"
                                  style={{
                                    fontFamily:
                                      "var(--font-poppins), Poppins, sans-serif",
                                    fontSize: "11px",
                                    fontWeight: 500,
                                    color: "rgba(255,255,255,0.5)",
                                    background: "rgba(255,255,255,0.05)",
                                    border: "1px solid rgba(255,255,255,0.08)",
                                    borderRadius: "6px",
                                    padding: "3px 8px",
                                    whiteSpace: "nowrap",
                                  }}
                                >
                                  <span
                                    className="w-1.5 h-1.5 rounded-full shrink-0"
                                    style={{ background: dotColor }}
                                  />
                                  {zone}
                                </span>
                                {result.found_on_pages && result.found_on_pages.length > 1 && (
                                  <span
                                    style={{
                                      fontFamily: "var(--font-poppins), Poppins, sans-serif",
                                      fontSize: "10px",
                                      fontWeight: 500,
                                      color: "#9d8cff",
                                      background: "rgba(124,108,255,0.1)",
                                      borderRadius: "4px",
                                      padding: "1px 5px",
                                      border: "1px solid rgba(124,108,255,0.2)",
                                    }}
                                  >
                                    {result.found_on_pages.length} pages
                                  </span>
                                )}
                              </div>
                            </td>

                            {/* Response time — tinted by latency threshold. */}
                            <td style={{ padding: "10px 16px", verticalAlign: "middle" }}>
                              <span
                                className="font-mono"
                                style={{
                                  fontSize: "12px",
                                  color: latencyColor(result.response_ms),
                                  fontVariantNumeric: "tabular-nums",
                                }}
                              >
                                {result.response_ms}ms
                              </span>
                            </td>

                            {/* Expand chevron */}
                            <td
                              style={{
                                padding: "10px 16px",
                                verticalAlign: "middle",
                                textAlign: "right",
                              }}
                            >
                              {isExpanded ? (
                                <ChevronUp
                                  size={14}
                                  style={{ color: "rgba(255,255,255,0.4)" }}
                                />
                              ) : (
                                <ChevronDown
                                  size={14}
                                  style={{ color: "rgba(255,255,255,0.2)" }}
                                />
                              )}
                            </td>
                          </motion.tr>,

                          /* Expanded detail row */
                          <AnimatePresence key={`detail-${rowKey}`}>
                            {isExpanded && <RowDetail result={result} />}
                          </AnimatePresence>,
                        ];
                      })),
                ];
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
