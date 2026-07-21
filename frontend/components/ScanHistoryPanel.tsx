"use client";

import { useState, useMemo, forwardRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp, Clock, TrendingUp } from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
} from "recharts";
import { LinkResult } from "@/types";

// ─── Types ────────────────────────────────────────────────────────────────────
interface ScanHistoryEntry {
  id: string;
  scanned_at: string;
  total_links: number;
  broken_count: number;
  dead_cta_count: number;
  health_score: number;
  results_json: LinkResult[];
}

interface ScanHistoryPanelProps {
  history: ScanHistoryEntry[];
  loading?: boolean;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function timeAgo(dateStr: string): string {
  const now = new Date();
  const d = new Date(dateStr);
  const diffMs = now.getTime() - d.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffDay === 0) {
    if (diffHr === 0) {
      if (diffMin < 2) return "just now";
      return `${diffMin} min ago`;
    }
    return `${diffHr}h ago`;
  }
  if (diffDay === 1) return "yesterday";
  if (diffDay < 7) return `${diffDay} days ago`;

  // Fallback to formatted date
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatChartDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function scoreColor(score: number): { bg: string; text: string } {
  if (score >= 90) return { bg: "rgba(76,175,125,0.15)", text: "#4caf7d" };
  if (score >= 70) return { bg: "rgba(245,166,35,0.15)", text: "#f5a623" };
  return { bg: "rgba(224,92,92,0.15)", text: "#e05c5c" };
}

// ─── Custom Recharts Tooltip ──────────────────────────────────────────────────
interface ChartPayloadItem {
  value: number;
  payload: { date: string; score: number };
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: ChartPayloadItem[];
}

function CustomChartTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const data = payload[0];
  return (
    <div
      style={{
        background: "var(--surface-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: 8,
        padding: "8px 12px",
        boxShadow: "var(--elev-3)",
      }}
    >
      <p
        style={{
          margin: 0,
          fontFamily: "var(--font-poppins), Poppins, sans-serif",
          fontSize: "13px",
          fontWeight: 600,
          color: "var(--signal)",
        }}
      >
        Health: {data.value}/100
      </p>
      <p
        style={{
          margin: "2px 0 0",
          fontFamily: "var(--font-poppins), Poppins, sans-serif",
          fontSize: "11px",
          color: "var(--text-muted)",
        }}
      >
        {data.payload.date}
      </p>
    </div>
  );
}

// ─── Expanded row showing broken links from a historical scan ─────────────────
function HistoryBrokenList({ scan }: { scan: ScanHistoryEntry }) {
  const brokenLinks = useMemo(() => {
    if (!scan.results_json) return [];
    return scan.results_json.filter(
      (r: LinkResult) =>
        r.label === "broken" || r.label === "dead_cta" || r.label === "error"
    );
  }, [scan.results_json]);

  if (brokenLinks.length === 0) {
    return (
      <div style={{ padding: "8px 0" }}>
        <p
          style={{
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
            fontSize: "12px",
            color: "var(--text-muted)",
            fontStyle: "italic",
          }}
        >
          No broken links in this scan ✓
        </p>
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 4,
        padding: "8px 0",
      }}
    >
      {brokenLinks.slice(0, 20).map((r: LinkResult, i: number) => {
        let displayUrl = r.url;
        try {
          const u = new URL(r.url);
          displayUrl = u.pathname + u.search;
          if (displayUrl.length > 60) displayUrl = displayUrl.slice(0, 60) + "…";
        } catch {
          if (displayUrl.length > 60) displayUrl = displayUrl.slice(0, 60) + "…";
        }

        const labelColors: Record<string, string> = {
          broken: "#e05c5c",
          dead_cta: "#f5a623",
          error: "#e05c5c",
        };

        return (
          <div
            key={`hist-broken-${i}`}
            className="flex items-center gap-2"
            style={{ fontSize: "11px" }}
          >
            <span
              style={{
                color: labelColors[r.label] ?? "#e05c5c",
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontWeight: 600,
                fontSize: "10px",
                textTransform: "uppercase",
                minWidth: 48,
              }}
            >
              {r.label === "dead_cta" ? "DEAD CTA" : r.label.toUpperCase()}
            </span>
            <span
              title={r.url}
              style={{
                fontFamily: "monospace",
                fontSize: "11px",
                color: "var(--text-muted)",
                wordBreak: "break-all",
              }}
            >
              {displayUrl}
            </span>
          </div>
        );
      })}
      {brokenLinks.length > 20 && (
        <p
          style={{
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
            fontSize: "11px",
            color: "var(--text-muted)",
            marginTop: 4,
          }}
        >
          + {brokenLinks.length - 20} more
        </p>
      )}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
const ScanHistoryPanel = forwardRef<HTMLElement, ScanHistoryPanelProps>(
  function ScanHistoryPanel({ history, loading = false }, ref) {
    const [collapsed, setCollapsed] = useState(true);
    const [expandedScanId, setExpandedScanId] = useState<string | null>(null);

    // Chart data: oldest → newest (reverse history since it comes desc)
    const chartData = useMemo(() => {
      return [...history]
        .reverse()
        .map((scan) => ({
          date: formatChartDate(scan.scanned_at),
          score: scan.health_score,
          fullDate: new Date(scan.scanned_at).toLocaleDateString("en-US", {
            month: "long",
            day: "numeric",
            year: "numeric",
          }),
        }));
    }, [history]);

    const showChart = chartData.length >= 2;

    if (loading) {
      return (
        <section ref={ref} className="relative z-10 px-4 pb-20">
          <div className="w-full max-w-5xl mx-auto mt-6">
            <div className="glass-card p-6 flex items-center justify-center gap-3">
              <div
                className="animate-spin"
                style={{
                  width: 18,
                  height: 18,
                  border: "2px solid var(--border-subtle)",
                  borderTopColor: "var(--signal)",
                  borderRadius: "50%",
                }}
              />
              <span
                style={{
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                  fontSize: "13px",
                  color: "var(--text-muted)",
                }}
              >
                Loading scan history…
              </span>
            </div>
          </div>
        </section>
      );
    }

    return (
      <section ref={ref} className="relative z-10 px-4 pb-20">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className="w-full max-w-5xl mx-auto mt-6"
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
                padding: "16px 20px",
                background: "transparent",
                border: "none",
                cursor: "pointer",
                borderBottom: collapsed
                  ? "none"
                  : "1px solid var(--border-subtle)",
              }}
            >
              <div className="flex items-center gap-3">
                <Clock size={18} style={{ color: "var(--signal)" }} />
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
                    📊 Scan History
                  </p>
                  <p
                    style={{
                      fontFamily: "var(--font-poppins), Poppins, sans-serif",
                      fontWeight: 400,
                      fontSize: "11px",
                      color: "var(--text-muted)",
                      margin: 0,
                    }}
                  >
                    {history.length > 0
                      ? `${history.length} previous scan${history.length !== 1 ? "s" : ""}`
                      : "No scan history yet"}
                  </p>
                </div>
              </div>
              {collapsed ? (
                <ChevronDown
                  size={16}
                  style={{ color: "var(--text-muted)" }}
                />
              ) : (
                <ChevronUp
                  size={16}
                  style={{ color: "var(--text-muted)" }}
                />
              )}
            </button>

            {/* Body */}
            <AnimatePresence>
              {!collapsed && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.3 }}
                  style={{ overflow: "hidden" }}
                >
                  <div style={{ padding: "0 20px 20px" }}>
                    {history.length === 0 ? (
                      /* Empty state */
                      <div
                        className="flex flex-col items-center gap-3 py-8"
                        style={{ textAlign: "center" }}
                      >
                        <Clock
                          size={32}
                          style={{ color: "var(--border-strong)" }}
                        />
                        <p
                          style={{
                            fontFamily:
                              "var(--font-poppins), Poppins, sans-serif",
                            fontSize: "14px",
                            fontWeight: 500,
                            color: "var(--text-muted)",
                            margin: 0,
                          }}
                        >
                          No previous scans found.
                        </p>
                        <p
                          style={{
                            fontFamily:
                              "var(--font-poppins), Poppins, sans-serif",
                            fontSize: "12px",
                            color: "var(--text-muted)",
                            margin: 0,
                          }}
                        >
                          Scan this site again to start tracking history.
                        </p>
                      </div>
                    ) : (
                      <>
                        {/* Health Score Chart */}
                        <div style={{ marginBottom: 20, marginTop: 8 }}>
                          {showChart ? (
                            <div>
                              <div
                                className="flex items-center gap-2 mb-3"
                                style={{ paddingLeft: 4 }}
                              >
                                <TrendingUp
                                  size={14}
                                  style={{ color: "var(--signal)" }}
                                />
                                <span
                                  style={{
                                    fontFamily:
                                      "var(--font-poppins), Poppins, sans-serif",
                                    fontSize: "12px",
                                    fontWeight: 500,
                                    color: "var(--text-muted)",
                                  }}
                                >
                                  Health Score Trend
                                </span>
                              </div>
                              <ResponsiveContainer width="100%" height={160}>
                                <LineChart
                                  data={chartData}
                                  margin={{
                                    top: 8,
                                    right: 16,
                                    bottom: 4,
                                    left: -20,
                                  }}
                                >
                                  <XAxis
                                    dataKey="date"
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{
                                      fontSize: 10,
                                      fill: "var(--text-muted)",
                                      fontFamily:
                                        "var(--font-poppins), Poppins, sans-serif",
                                    }}
                                  />
                                  <YAxis
                                    domain={[0, 100]}
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{
                                      fontSize: 10,
                                      fill: "var(--text-muted)",
                                      fontFamily:
                                        "var(--font-poppins), Poppins, sans-serif",
                                    }}
                                  />
                                  <RechartsTooltip
                                    content={<CustomChartTooltip />}
                                    cursor={{
                                      stroke: "rgba(79,70,229,0.2)",
                                    }}
                                  />
                                  <Line
                                    type="monotone"
                                    dataKey="score"
                                    stroke="var(--signal)"
                                    strokeWidth={2.5}
                                    dot={{
                                      fill: "var(--signal)",
                                      r: 4,
                                      strokeWidth: 0,
                                    }}
                                    activeDot={{
                                      fill: "var(--signal-bright)",
                                      r: 6,
                                      strokeWidth: 2,
                                      stroke: "var(--signal)",
                                    }}
                                  />
                                </LineChart>
                              </ResponsiveContainer>
                            </div>
                          ) : (
                            <div
                              className="flex items-center gap-2"
                              style={{
                                padding: "12px 14px",
                                borderRadius: 8,
                                background: "rgba(79,70,229,0.06)",
                                border: "1px solid rgba(79,70,229,0.12)",
                              }}
                            >
                              <TrendingUp
                                size={14}
                                style={{ color: "var(--signal)" }}
                              />
                              <span
                                style={{
                                  fontFamily:
                                    "var(--font-poppins), Poppins, sans-serif",
                                  fontSize: "12px",
                                  color: "var(--text-muted)",
                                }}
                              >
                                Scan again to see your health trend
                              </span>
                            </div>
                          )}
                        </div>

                        {/* History Table */}
                        <div
                          className="overflow-x-auto"
                          style={{ borderRadius: 8 }}
                        >
                          <table
                            style={{
                              width: "100%",
                              borderCollapse: "collapse",
                              minWidth: 500,
                            }}
                          >
                            <thead>
                              <tr
                                style={{
                                  borderBottom:
                                    "1px solid var(--border-subtle)",
                                }}
                              >
                                {[
                                  "Date",
                                  "Total Links",
                                  "Broken",
                                  "Dead CTAs",
                                  "Health Score",
                                ].map((col) => (
                                  <th
                                    key={col}
                                    style={{
                                      padding: "8px 12px",
                                      textAlign: "left",
                                      fontSize: "10px",
                                      textTransform: "uppercase",
                                      letterSpacing: "0.08em",
                                      color: "var(--text-muted)",
                                      fontFamily:
                                        "var(--font-poppins), Poppins, sans-serif",
                                      fontWeight: 500,
                                      whiteSpace: "nowrap",
                                    }}
                                  >
                                    {col}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {history.map((scan) => {
                                const sc = scoreColor(scan.health_score);
                                const isExpanded =
                                  expandedScanId === scan.id;

                                return [
                                  <tr
                                    key={scan.id}
                                    onClick={() =>
                                      setExpandedScanId(
                                        isExpanded ? null : scan.id
                                      )
                                    }
                                    style={{
                                      cursor: "pointer",
                                      borderBottom:
                                        "1px solid var(--border-subtle)",
                                      background: isExpanded
                                        ? "rgba(28,28,46,0.04)"
                                        : "transparent",
                                      transition: "background 0.15s",
                                    }}
                                    onMouseEnter={(e) => {
                                      if (!isExpanded)
                                        (
                                          e.currentTarget as HTMLElement
                                        ).style.background =
                                          "rgba(28,28,46,0.03)";
                                    }}
                                    onMouseLeave={(e) => {
                                      if (!isExpanded)
                                        (
                                          e.currentTarget as HTMLElement
                                        ).style.background = "transparent";
                                    }}
                                  >
                                    {/* Date */}
                                    <td
                                      style={{
                                        padding: "10px 12px",
                                        fontFamily:
                                          "var(--font-poppins), Poppins, sans-serif",
                                        fontSize: "12px",
                                        color: "var(--text-secondary)",
                                        whiteSpace: "nowrap",
                                      }}
                                    >
                                      {timeAgo(scan.scanned_at)}
                                    </td>

                                    {/* Total Links */}
                                    <td
                                      style={{
                                        padding: "10px 12px",
                                        fontFamily:
                                          "var(--font-poppins), Poppins, sans-serif",
                                        fontSize: "12px",
                                        color: "var(--text-muted)",
                                        fontVariantNumeric: "tabular-nums",
                                      }}
                                    >
                                      {scan.total_links}
                                    </td>

                                    {/* Broken */}
                                    <td
                                      style={{
                                        padding: "10px 12px",
                                        fontFamily:
                                          "var(--font-poppins), Poppins, sans-serif",
                                        fontSize: "12px",
                                        color:
                                          scan.broken_count > 0
                                            ? "#e05c5c"
                                            : "var(--text-muted)",
                                        fontWeight:
                                          scan.broken_count > 0 ? 600 : 400,
                                        fontVariantNumeric: "tabular-nums",
                                      }}
                                    >
                                      {scan.broken_count}
                                    </td>

                                    {/* Dead CTAs */}
                                    <td
                                      style={{
                                        padding: "10px 12px",
                                        fontFamily:
                                          "var(--font-poppins), Poppins, sans-serif",
                                        fontSize: "12px",
                                        color:
                                          scan.dead_cta_count > 0
                                            ? "#f5a623"
                                            : "var(--text-muted)",
                                        fontWeight:
                                          scan.dead_cta_count > 0 ? 600 : 400,
                                        fontVariantNumeric: "tabular-nums",
                                      }}
                                    >
                                      {scan.dead_cta_count}
                                    </td>

                                    {/* Health Score Pill */}
                                    <td style={{ padding: "10px 12px" }}>
                                      <span
                                        style={{
                                          display: "inline-flex",
                                          alignItems: "center",
                                          padding: "3px 10px",
                                          borderRadius: 20,
                                          fontSize: "11px",
                                          fontWeight: 600,
                                          fontFamily:
                                            "var(--font-poppins), Poppins, sans-serif",
                                          background: sc.bg,
                                          color: sc.text,
                                          fontVariantNumeric: "tabular-nums",
                                        }}
                                      >
                                        {scan.health_score}/100
                                      </span>
                                    </td>
                                  </tr>,

                                  /* Expanded detail */
                                  <AnimatePresence
                                    key={`detail-${scan.id}`}
                                  >
                                    {isExpanded && (
                                      <motion.tr
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        exit={{ opacity: 0 }}
                                        transition={{ duration: 0.15 }}
                                      >
                                        <td
                                          colSpan={5}
                                          style={{
                                            padding: "4px 12px 12px 24px",
                                            borderBottom:
                                              "1px solid var(--border-subtle)",
                                            background:
                                              "rgba(28,28,46,0.03)",
                                          }}
                                        >
                                          <HistoryBrokenList scan={scan} />
                                        </td>
                                      </motion.tr>
                                    )}
                                  </AnimatePresence>,
                                ];
                              })}
                            </tbody>
                          </table>
                        </div>
                      </>
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
);

export default ScanHistoryPanel;
