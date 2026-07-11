"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import { LinkResult } from "@/types";

interface ScanHistoryEntry {
  id: string;
  scanned_at: string;
  total_links: number;
  broken_count: number;
  dead_cta_count: number;
  health_score: number;
  results_json: LinkResult[];
}

interface WhatChangedCardProps {
  currentResults: LinkResult[];
  history: ScanHistoryEntry[];
}

interface DiffLink {
  url: string;
  label: string;
  category: string;
  /** How many scans ago this was first seen broken */
  brokenSince?: number;
}

function StatusPillMini({ label }: { label: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    broken: { bg: "rgba(248,113,113,0.15)", text: "#f87171" },
    dead_cta: { bg: "rgba(251,191,36,0.15)", text: "#fbbf24" },
    error: { bg: "rgba(248,113,113,0.15)", text: "#f87171" },
    timeout: { bg: "rgba(251,146,60,0.15)", text: "#fb923c" },
    blocked: { bg: "rgba(148,163,184,0.15)", text: "#94a3b8" },
  };
  const style = colors[label] ?? { bg: "rgba(255,255,255,0.08)", text: "rgba(255,255,255,0.5)" };

  const labelMap: Record<string, string> = {
    broken: "Broken",
    dead_cta: "Dead CTA",
    error: "Error",
    timeout: "Timeout",
    blocked: "Blocked",
  };

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "2px 8px",
        borderRadius: 6,
        fontSize: "10px",
        fontWeight: 600,
        fontFamily: "var(--font-poppins), Poppins, sans-serif",
        background: style.bg,
        color: style.text,
        textTransform: "uppercase",
        letterSpacing: "0.04em",
      }}
    >
      {labelMap[label] ?? label}
    </span>
  );
}

function ZoneBadge({ zone }: { zone: string }) {
  const ZONE_DOT_COLORS: Record<string, string> = {
    Navigation: "#60a5fa",
    Header: "#a855f7",
    Footer: "#94a3b8",
    CTA: "#fbbf24",
    "Body text": "#e2e8f0",
    Other: "#64748b",
    "Dead CTA": "#f87171",
  };
  const dotColor = ZONE_DOT_COLORS[zone] ?? "#64748b";

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "2px 8px",
        borderRadius: 6,
        fontSize: "10px",
        fontWeight: 500,
        fontFamily: "var(--font-poppins), Poppins, sans-serif",
        background: "rgba(255,255,255,0.05)",
        border: "1px solid rgba(255,255,255,0.08)",
        color: "rgba(255,255,255,0.5)",
      }}
    >
      <span
        style={{
          width: 5,
          height: 5,
          borderRadius: "50%",
          background: dotColor,
          flexShrink: 0,
        }}
      />
      {zone}
    </span>
  );
}

function TruncatedUrl({ url }: { url: string }) {
  let display = url;
  try {
    const u = new URL(url);
    display = u.pathname + u.search;
    if (display.length > 50) display = display.slice(0, 50) + "…";
  } catch {
    if (display.length > 50) display = display.slice(0, 50) + "…";
  }

  return (
    <span
      title={url}
      style={{
        fontFamily: "monospace",
        fontSize: "11px",
        color: "rgba(255,255,255,0.6)",
        wordBreak: "break-all",
      }}
    >
      {display}
    </span>
  );
}

export default function WhatChangedCard({
  currentResults,
  history,
}: WhatChangedCardProps) {
  // We need at least 1 previous scan to compare
  if (history.length < 1) return null;

  const previousScan = history[0]; // Most recent previous scan

  const diff = useMemo(() => {
    const prevResults = previousScan.results_json ?? [];

    // Build sets of broken/dead URLs from current and previous
    const currentIssueUrls = new Map<string, LinkResult>();
    const prevIssueUrls = new Map<string, LinkResult>();

    for (const r of currentResults) {
      if (r.label === "broken" || r.label === "dead_cta" || r.label === "error") {
        currentIssueUrls.set(r.url, r);
      }
    }

    for (const r of prevResults) {
      if (r.label === "broken" || r.label === "dead_cta" || r.label === "error") {
        prevIssueUrls.set(r.url, r);
      }
    }

    // New issues: in current but not in previous
    const newIssues: DiffLink[] = [];
    currentIssueUrls.forEach((r, url) => {
      if (!prevIssueUrls.has(url)) {
        newIssues.push({ url, label: r.label, category: r.category });
      }
    });

    // Fixed: in previous but not in current
    const fixed: DiffLink[] = [];
    prevIssueUrls.forEach((r, url) => {
      if (!currentIssueUrls.has(url)) {
        fixed.push({ url, label: r.label, category: r.category });
      }
    });

    // Still broken: in both
    const stillBroken: DiffLink[] = [];
    currentIssueUrls.forEach((r, url) => {
      if (prevIssueUrls.has(url)) {
        // Count how many consecutive previous scans had this issue
        let brokenSince = 1;
        for (const scan of history) {
          const scanResults = scan.results_json ?? [];
          const found = scanResults.find(
            (sr: LinkResult) =>
              sr.url === url &&
              (sr.label === "broken" || sr.label === "dead_cta" || sr.label === "error")
          );
          if (found) {
            brokenSince++;
          } else {
            break;
          }
        }
        stillBroken.push({
          url,
          label: r.label,
          category: r.category,
          brokenSince,
        });
      }
    });

    return { newIssues, fixed, stillBroken };
  }, [currentResults, history, previousScan]);

  const hasChanges =
    diff.newIssues.length > 0 ||
    diff.fixed.length > 0 ||
    diff.stillBroken.length > 0;

  const [collapsed, setCollapsed] = useState(!hasChanges);

  const pluralize = (n: number, word: string) =>
    `${n} ${word}${n !== 1 ? "s" : ""}`;

  return (
    <section className="relative z-10 px-4 mb-2">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="w-full max-w-3xl mx-auto"
      >
        <div className="glass-card overflow-hidden">
          {/* Header */}
          <button
            onClick={() => setCollapsed((p) => !p)}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "14px 20px",
              background: "transparent",
              border: "none",
              cursor: "pointer",
              borderBottom: collapsed
                ? "none"
                : "1px solid rgba(255,255,255,0.06)",
            }}
          >
            <div className="flex items-center gap-3">
              <span style={{ fontSize: "16px" }}>🔄</span>
              <div style={{ textAlign: "left" }}>
                <p
                  style={{
                    fontFamily: "var(--font-poppins), Poppins, sans-serif",
                    fontWeight: 600,
                    fontSize: "14px",
                    color: "white",
                    margin: 0,
                    lineHeight: 1.3,
                  }}
                >
                  What Changed
                </p>
                <p
                  style={{
                    fontFamily: "var(--font-poppins), Poppins, sans-serif",
                    fontWeight: 400,
                    fontSize: "11px",
                    color: "rgba(255,255,255,0.4)",
                    margin: 0,
                    lineHeight: 1.4,
                  }}
                >
                  {hasChanges
                    ? `${diff.newIssues.length} new · ${diff.fixed.length} fixed · ${diff.stillBroken.length} persisting`
                    : "No changes since last scan"}
                </p>
              </div>
            </div>
            {collapsed ? (
              <ChevronDown size={16} style={{ color: "rgba(255,255,255,0.3)" }} />
            ) : (
              <ChevronUp size={16} style={{ color: "rgba(255,255,255,0.3)" }} />
            )}
          </button>

          {/* Body */}
          <AnimatePresence>
            {!collapsed && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25 }}
                style={{ overflow: "hidden" }}
              >
                <div style={{ padding: "0 20px 18px" }}>
                  {!hasChanges ? (
                    <div
                      className="flex items-center gap-2"
                      style={{ padding: "12px 0" }}
                    >
                      <Sparkles size={16} style={{ color: "#a855f7" }} />
                      <span
                        style={{
                          fontFamily:
                            "var(--font-poppins), Poppins, sans-serif",
                          fontSize: "13px",
                          fontWeight: 500,
                          color: "rgba(255,255,255,0.65)",
                        }}
                      >
                        ✨ No changes since last scan
                      </span>
                    </div>
                  ) : (
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: 16,
                        paddingTop: 4,
                      }}
                    >
                      {/* New Issues */}
                      {diff.newIssues.length > 0 && (
                        <div>
                          <p
                            style={{
                              fontFamily:
                                "var(--font-poppins), Poppins, sans-serif",
                              fontWeight: 600,
                              fontSize: "12px",
                              color: "#f87171",
                              margin: "0 0 8px 0",
                            }}
                          >
                            🆕 {pluralize(diff.newIssues.length, "new issue")}{" "}
                            since last scan
                          </p>
                          <div
                            style={{
                              display: "flex",
                              flexDirection: "column",
                              gap: 6,
                            }}
                          >
                            {diff.newIssues.map((item, i) => (
                              <div
                                key={`new-${i}`}
                                className="flex items-center gap-2 flex-wrap"
                                style={{
                                  padding: "6px 10px",
                                  borderRadius: 8,
                                  background: "rgba(248,113,113,0.06)",
                                  border: "1px solid rgba(248,113,113,0.12)",
                                }}
                              >
                                <StatusPillMini label={item.label} />
                                <TruncatedUrl url={item.url} />
                                <ZoneBadge zone={item.category} />
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Fixed */}
                      {diff.fixed.length > 0 && (
                        <div>
                          <p
                            style={{
                              fontFamily:
                                "var(--font-poppins), Poppins, sans-serif",
                              fontWeight: 600,
                              fontSize: "12px",
                              color: "#4ade80",
                              margin: "0 0 8px 0",
                            }}
                          >
                            ✅ {pluralize(diff.fixed.length, "issue")} fixed
                            since last scan
                          </p>
                          <div
                            style={{
                              display: "flex",
                              flexDirection: "column",
                              gap: 6,
                            }}
                          >
                            {diff.fixed.map((item, i) => (
                              <div
                                key={`fix-${i}`}
                                className="flex items-center gap-2 flex-wrap"
                                style={{
                                  padding: "6px 10px",
                                  borderRadius: 8,
                                  background: "rgba(74,222,128,0.06)",
                                  border: "1px solid rgba(74,222,128,0.12)",
                                }}
                              >
                                <TruncatedUrl url={item.url} />
                                <ZoneBadge zone={item.category} />
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Still Broken */}
                      {diff.stillBroken.length > 0 && (
                        <div>
                          <p
                            style={{
                              fontFamily:
                                "var(--font-poppins), Poppins, sans-serif",
                              fontWeight: 600,
                              fontSize: "12px",
                              color: "#fb923c",
                              margin: "0 0 8px 0",
                            }}
                          >
                            ⚠️ {pluralize(diff.stillBroken.length, "persisting issue")}
                          </p>
                          <div
                            style={{
                              display: "flex",
                              flexDirection: "column",
                              gap: 6,
                            }}
                          >
                            {diff.stillBroken.map((item, i) => (
                              <div
                                key={`still-${i}`}
                                className="flex items-center gap-2 flex-wrap"
                                style={{
                                  padding: "6px 10px",
                                  borderRadius: 8,
                                  background: "rgba(251,146,60,0.06)",
                                  border: "1px solid rgba(251,146,60,0.12)",
                                }}
                              >
                                <StatusPillMini label={item.label} />
                                <TruncatedUrl url={item.url} />
                                <ZoneBadge zone={item.category} />
                                {item.brokenSince && item.brokenSince > 1 && (
                                  <span
                                    style={{
                                      fontFamily:
                                        "var(--font-poppins), Poppins, sans-serif",
                                      fontSize: "10px",
                                      color: "rgba(255,255,255,0.35)",
                                      fontStyle: "italic",
                                    }}
                                  >
                                    broken for {item.brokenSince} scan
                                    {item.brokenSince !== 1 ? "s" : ""}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </section>
  );
}
