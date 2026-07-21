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
} from "lucide-react";
import { LinkResult, SortOption } from "@/types";
import StatusPill from "./StatusPill";
import ExportButton from "./ExportButton";
import PriorityBadge from "./PriorityBadge";
import SuggestionCard from "./SuggestionCard";
import RedirectDownloadButton from "./RedirectDownload";

interface ResultsTableProps {
  results: LinkResult[];
  sortOption: SortOption;
  scannedUrl?: string;
  healthScore?: number;
}

// ─── Zone config ─────────────────────────────────────────────────────────────
const ZONE_ORDER = [
  "Navigation",
  "Header",
  "CTA",
  "Body text",
  "Footer",
  "Other",
  "Dead CTA",
];

const ZONE_DOT_COLORS: Record<string, string> = {
  Navigation: "#5b8def",
  Header: "#4f46e5",
  Footer: "#7a7a8c",
  CTA: "#f5a623",
  "Body text": "#94949f",
  Other: "#7a7a8c",
  "Dead CTA": "#e05c5c",
};

// ─── Row status styling ───────────────────────────────────────────────────────
const ROW_ACCENT: Record<
  string,
  { border: string; bg: string } | undefined
> = {
  broken: { border: "#e05c5c", bg: "rgba(224,92,92,0.05)" },
  error: { border: "#e05c5c", bg: "rgba(224,92,92,0.05)" },
  dead_cta: { border: "#f5a623", bg: "rgba(245,166,35,0.05)" },
  redirect: { border: "#f5a623", bg: "rgba(245,166,35,0.04)" },
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
        colSpan={7}
        style={{ padding: 0, borderBottom: "1px solid var(--color-border-soft)" }}
      >
        <div
          style={{
            padding: "14px 20px 14px 36px",
            background: "var(--color-card-soft)",
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
                color: "var(--color-text-secondary)",
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
                <Check size={13} style={{ color: "var(--color-success)" }} />
              ) : (
                <Copy size={13} style={{ color: "var(--color-text-muted)" }} />
              )}
            </button>
            <a
              href={result.url}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 transition-opacity hover:opacity-80"
            >
              <ExternalLink size={13} style={{ color: "var(--color-text-muted)" }} />
            </a>
          </div>

          {/* Final URL if redirect */}
          {result.final_url && result.final_url !== result.url && (
            <div className="flex items-center gap-2">
              <span style={{ fontSize: "11px", color: "var(--color-text-muted)" }}>
                Final destination:
              </span>
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: "12px",
                  color: "#f5a623",
                  wordBreak: "break-all",
                }}
              >
                {result.final_url}
              </span>
            </div>
          )}

          {/* Meta row */}
          <div className="flex flex-wrap gap-4">
            {result.status_code && (
              <span style={{ fontSize: "11px", color: "var(--color-text-muted)" }}>
                HTTP {result.status_code}
              </span>
            )}
            {result.source_element && (
              <span
                style={{
                  fontFamily: "monospace",
                  fontSize: "11px",
                  color: "var(--color-text-muted)",
                }}
              >
                {result.source_element}
              </span>
            )}
            <span style={{ fontSize: "11px", color: "var(--color-text-muted)" }}>
              {result.response_ms}ms
            </span>
          </div>

          {/* AI Suggestion Card (Upgrade 3) */}
          {result.suggestion && (
            <SuggestionCard suggestion={result.suggestion} url={result.url} />
          )}

          {/* Basic suggestion fallback */}
          {basicSuggestion && !result.suggestion && (
            <div
              className="flex items-start gap-2 mt-1 rounded-lg px-3 py-2"
              style={{
                background: "rgba(245,166,35,0.06)",
                border: "1px solid rgba(245,166,35,0.2)",
              }}
            >
              <AlertCircle size={13} style={{ color: "#f5a623", marginTop: 2, flexShrink: 0 }} />
              <span
                style={{
                  fontSize: "12px",
                  color: "var(--color-text-secondary)",
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
            <circle cx="40" cy="40" r="36" stroke="var(--color-border-soft)" strokeWidth="2" />
            <circle cx="40" cy="40" r="24" stroke="var(--color-border-soft)" strokeWidth="2" />
            <line x1="25" y1="55" x2="55" y2="25" stroke="var(--color-text-muted)" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <div>
            <p
              className="text-text-primary"
              style={{ fontWeight: 600, fontSize: "18px", marginBottom: 6 }}
            >
              No links matched this filter
            </p>
            <p className="text-text-muted" style={{ fontSize: "14px" }}>
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
              background: "var(--color-text-primary)",
              border: "1px solid rgba(76,175,125,0.4)",
              fontSize: "13px",
              fontWeight: 500,
              color: "#5fca97",
              boxShadow: "var(--shadow-lg)",
            }}
          >
            <Check size={14} />
            Copied!
          </motion.div>
        )}
      </AnimatePresence>

      <div className="glass-card overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-soft">
          <h3
            className="text-text-secondary"
            style={{ fontWeight: 500, fontSize: "14px" }}
          >
            Results
          </h3>
          <div className="flex items-center gap-2">
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
              <tr style={{ borderBottom: "1px solid var(--color-border-soft)" }}>
                {["Status", "Priority", "Link Text", "URL", "Where on Page", "Time", ""].map(
                  (col) => (
                    <th
                      key={col}
                      className="px-4 py-3 text-left text-text-muted"
                      style={{
                        fontSize: "10px",
                        textTransform: "uppercase",
                        letterSpacing: "0.08em",
                        fontWeight: 600,
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
                      background: "var(--color-card-soft)",
                      borderBottom: "1px solid var(--color-border-soft)",
                      borderTop: "1px solid var(--color-border-soft)",
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLTableRowElement).style.background =
                        "rgba(28,28,46,0.05)";
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLTableRowElement).style.background =
                        "var(--color-card-soft)";
                    }}
                  >
                    <td colSpan={7} style={{ padding: "8px 16px" }}>
                      <div className="flex items-center gap-3">
                        <span
                          className="w-2 h-2 rounded-full shrink-0"
                          style={{ background: dotColor }}
                        />
                        <span
                          className="text-text-secondary"
                          style={{
                            fontWeight: 600,
                            fontSize: "11px",
                            textTransform: "uppercase",
                            letterSpacing: "0.07em",
                          }}
                        >
                          {zone}
                        </span>
                        <span
                          className="text-text-muted"
                          style={{ fontSize: "11px" }}
                        >
                          {items.length} link{items.length !== 1 ? "s" : ""}
                          {issueCount > 0 && (
                            <span style={{ color: "#e05c5c", marginLeft: 4 }}>
                              · {issueCount} broken
                            </span>
                          )}
                        </span>
                        <span className="ml-auto">
                          {isCollapsed ? (
                            <ChevronDown size={14} style={{ color: "var(--color-text-muted)" }} />
                          ) : (
                            <ChevronUp size={14} style={{ color: "var(--color-text-muted)" }} />
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
                              borderBottom: "1px solid var(--color-border-soft)",
                              borderLeft: accent
                                ? `3px solid ${accent.border}`
                                : "3px solid transparent",
                              background: isExpanded
                                ? "var(--color-card-soft)"
                                : accent
                                ? accent.bg
                                : "transparent",
                              transition: "background 0.15s",
                            }}
                            onMouseEnter={(e) => {
                              if (!isExpanded)
                                (e.currentTarget as HTMLElement).style.background =
                                  "rgba(28,28,46,0.03)";
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

                            {/* Priority */}
                            <td style={{ padding: "10px 16px", verticalAlign: "middle" }}>
                              <PriorityBadge priority={result.priority} />
                            </td>

                            {/* Link text */}
                            <td style={{ padding: "10px 16px", verticalAlign: "middle" }}>
                              <span
                                className="text-text-primary"
                                style={{
                                  fontSize: "13px",
                                  fontWeight: 400,
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
                                      color: "var(--color-text-muted)",
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
                                      color: "var(--color-text-secondary)",
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
                                      <Check size={12} style={{ color: "var(--color-success)" }} />
                                    ) : (
                                      <Copy
                                        size={12}
                                        style={{ color: "var(--color-text-muted)" }}
                                      />
                                    )}
                                  </button>
                                </div>
                              </div>
                            </td>

                            {/* Zone badge */}
                            <td style={{ padding: "10px 16px", verticalAlign: "middle" }}>
                              <span
                                className="inline-flex items-center gap-1.5"
                                style={{
                                  fontSize: "11px",
                                  fontWeight: 500,
                                  color: "var(--color-text-secondary)",
                                  background: "var(--color-card-soft)",
                                  border: "1px solid var(--color-border-soft)",
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
                            </td>

                            {/* Response time */}
                            <td style={{ padding: "10px 16px", verticalAlign: "middle" }}>
                              <span
                                className="text-text-muted"
                                style={{
                                  fontSize: "12px",
                                  fontWeight: 400,
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
                                  style={{ color: "var(--color-text-secondary)" }}
                                />
                              ) : (
                                <ChevronDown
                                  size={14}
                                  style={{ color: "var(--color-text-muted)" }}
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
