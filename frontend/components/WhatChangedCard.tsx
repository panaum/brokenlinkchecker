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
    broken: { bg: "rgba(224,92,92,0.15)", text: "#e05c5c" },
    dead_cta: { bg: "rgba(245,166,35,0.15)", text: "#f5a623" },
    error: { bg: "rgba(224,92,92,0.15)", text: "#e05c5c" },
    timeout: { bg: "rgba(245,166,35,0.15)", text: "#f5a623" },
    blocked: { bg: "rgba(122,122,140,0.15)", text: "#7a7a8c" },
  };
  const style = colors[label] ?? { bg: "rgba(28,28,46,0.06)", text: "var(--text-muted)" };

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
    Navigation: "#7a7a8c",
    Header: "#4f46e5",
    Footer: "#7a7a8c",
    CTA: "#f5a623",
    "Body text": "#1c1c2e",
    Other: "#7a7a8c",
    "Dead CTA": "#e05c5c",
  };
  const dotColor = ZONE_DOT_COLORS[zone] ?? "#7a7a8c";

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
        background: "rgba(28,28,46,0.04)",
        border: "1px solid var(--border-subtle)",
        color: "var(--text-muted)",
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
        color: "var(--text-secondary)",
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
        className="ds-container w-full px-6"
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
                : "1px solid var(--border-subtle)",
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
                    color: "var(--text-primary)",
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
                    color: "var(--text-muted)",
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
              <ChevronDown size={16} style={{ color: "var(--text-muted)" }} />
            ) : (
              <ChevronUp size={16} style={{ color: "var(--text-muted)" }} />
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
                      <Sparkles size={16} style={{ color: "var(--signal)" }} />
                      <span
                        style={{
                          fontFamily:
                            "var(--font-poppins), Poppins, sans-serif",
                          fontSize: "13px",
                          fontWeight: 500,
                          color: "var(--text-secondary)",
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
                              color: "#e05c5c",
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
                                  background: "rgba(224,92,92,0.06)",
                                  border: "1px solid rgba(224,92,92,0.12)",
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
                              color: "#4caf7d",
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
                                  background: "rgba(76,175,125,0.06)",
                                  border: "1px solid rgba(76,175,125,0.12)",
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
                              color: "#f5a623",
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
                                  background: "rgba(245,166,35,0.06)",
                                  border: "1px solid rgba(245,166,35,0.12)",
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
                                      color: "var(--text-muted)",
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
