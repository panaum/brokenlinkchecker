"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TrendingUp, ChevronDown, ChevronUp } from "lucide-react";
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

interface ScanHistoryListProps {
  history: ScanHistoryEntry[];
}

// One collapsed run of consecutive identical scans, or a single scan row.
type RunItem =
  | { kind: "single"; scan: ScanHistoryEntry }
  | { kind: "run"; scans: ScanHistoryEntry[] };

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

function formatClockTime(dateStr: string): string {
  return new Date(dateStr).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

function sameCalendarDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

// "Identical" for run-collapsing: the four metrics we display are unchanged.
function sameMetrics(a: ScanHistoryEntry, b: ScanHistoryEntry): boolean {
  return (
    a.total_links === b.total_links &&
    a.broken_count === b.broken_count &&
    a.dead_cta_count === b.dead_cta_count &&
    a.health_score === b.health_score
  );
}

// Collapse consecutive identical scans into runs. The newest scan (history[0])
// and the oldest scan (history[last]) always stand alone as timeline anchors,
// even when they belong to a run. A run of >= 2 remaining scans becomes one
// collapsed row; a leftover single stays an individual row.
function buildRunItems(history: ScanHistoryEntry[]): RunItem[] {
  const n = history.length;
  if (n === 0) return [];

  const runs: ScanHistoryEntry[][] = [];
  for (let i = 0; i < n; i++) {
    if (i > 0 && sameMetrics(history[i], history[i - 1])) {
      runs[runs.length - 1].push(history[i]);
    } else {
      runs.push([history[i]]);
    }
  }

  const items: RunItem[] = [];
  runs.forEach((run, ri) => {
    let mid = run;
    let frontAnchor: ScanHistoryEntry | null = null;
    let backAnchor: ScanHistoryEntry | null = null;
    // The first run starts with the newest scan; the last run ends with the
    // oldest. Peel those out so they always render as their own rows.
    if (ri === 0) {
      frontAnchor = mid[0];
      mid = mid.slice(1);
    }
    if (ri === runs.length - 1 && mid.length > 0) {
      backAnchor = mid[mid.length - 1];
      mid = mid.slice(0, -1);
    }

    if (frontAnchor) items.push({ kind: "single", scan: frontAnchor });
    if (mid.length === 1) items.push({ kind: "single", scan: mid[0] });
    else if (mid.length >= 2) items.push({ kind: "run", scans: mid });
    if (backAnchor) items.push({ kind: "single", scan: backAnchor });
  });

  return items;
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

const POPPINS = "var(--font-poppins), Poppins, sans-serif";

// ─── Presentational history list (chart + table) ──────────────────────────────
// The card frame, collapse header, and loading/empty states live in the merged
// WhatChangedCard; this renders the health-score trend (>= 2 scans) and the
// per-scan table. On an unchanging site, consecutive identical scans collapse
// into a single "N scans with no change" row so 29 flat scans don't cost 29
// rows — toggle "Only show changes" off to see every scan.
export default function ScanHistoryList({ history }: ScanHistoryListProps) {
  const [expandedScanId, setExpandedScanId] = useState<string | null>(null);
  const [expandedRuns, setExpandedRuns] = useState<Set<string>>(new Set());
  const [onlyChanges, setOnlyChanges] = useState(true);

  // Every scan on the same calendar day → the date axis/spans would repeat
  // ("Jul 23" x29), so label with the time of day instead.
  const allSameDay = useMemo(
    () =>
      history.length > 0 &&
      history.every((s) =>
        sameCalendarDay(new Date(s.scanned_at), new Date(history[0].scanned_at))
      ),
    [history]
  );

  // Every scan the same health score → a flat 29-point line says nothing, so a
  // one-line note replaces the chart.
  const allSameScore = useMemo(
    () =>
      history.length > 0 &&
      history.every((s) => s.health_score === history[0].health_score),
    [history]
  );

  // Chart data: oldest → newest (reverse history since it comes desc).
  const chartData = useMemo(() => {
    return [...history]
      .reverse()
      .map((scan) => ({
        date: allSameDay
          ? formatClockTime(scan.scanned_at)
          : formatChartDate(scan.scanned_at),
        score: scan.health_score,
        fullDate: new Date(scan.scanned_at).toLocaleDateString("en-US", {
          month: "long",
          day: "numeric",
          year: "numeric",
        }),
      }));
  }, [history, allSameDay]);

  const showChart = chartData.length >= 2;

  const items = useMemo(() => buildRunItems(history), [history]);

  const toggleRun = (id: string) =>
    setExpandedRuns((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const runSpan = (run: ScanHistoryEntry[]): string => {
    const fmt = (s: string) =>
      allSameDay ? formatClockTime(s) : formatChartDate(s);
    const oldest = run[run.length - 1].scanned_at;
    const newest = run[0].scanned_at;
    return `${fmt(oldest)} – ${fmt(newest)}`;
  };

  // A single scan row + its (unchanged) per-row broken-link expansion.
  const scanRow = (scan: ScanHistoryEntry, indent = false) => {
    const sc = scoreColor(scan.health_score);
    const isExpanded = expandedScanId === scan.id;
    return [
      <tr
        key={scan.id}
        onClick={() => setExpandedScanId(isExpanded ? null : scan.id)}
        style={{
          cursor: "pointer",
          borderBottom: "1px solid var(--border-subtle)",
          background: isExpanded ? "rgba(28,28,46,0.04)" : "transparent",
          transition: "background 0.15s",
        }}
        onMouseEnter={(e) => {
          if (!isExpanded)
            (e.currentTarget as HTMLElement).style.background =
              "rgba(28,28,46,0.03)";
        }}
        onMouseLeave={(e) => {
          if (!isExpanded)
            (e.currentTarget as HTMLElement).style.background = "transparent";
        }}
      >
        <td
          style={{
            padding: "10px 12px",
            paddingLeft: indent ? 28 : 12,
            fontFamily: POPPINS,
            fontSize: "12px",
            color: "var(--text-secondary)",
            whiteSpace: "nowrap",
          }}
        >
          {timeAgo(scan.scanned_at)}
        </td>
        <td
          style={{
            padding: "10px 12px",
            fontFamily: POPPINS,
            fontSize: "12px",
            color: "var(--text-muted)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {scan.total_links}
        </td>
        <td
          style={{
            padding: "10px 12px",
            fontFamily: POPPINS,
            fontSize: "12px",
            color: scan.broken_count > 0 ? "#e05c5c" : "var(--text-muted)",
            fontWeight: scan.broken_count > 0 ? 600 : 400,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {scan.broken_count}
        </td>
        <td
          style={{
            padding: "10px 12px",
            fontFamily: POPPINS,
            fontSize: "12px",
            color: scan.dead_cta_count > 0 ? "#f5a623" : "var(--text-muted)",
            fontWeight: scan.dead_cta_count > 0 ? 600 : 400,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {scan.dead_cta_count}
        </td>
        <td style={{ padding: "10px 12px" }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              padding: "3px 10px",
              borderRadius: 20,
              fontSize: "11px",
              fontWeight: 600,
              fontFamily: POPPINS,
              background: sc.bg,
              color: sc.text,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {scan.health_score}/100
          </span>
        </td>
      </tr>,

      <AnimatePresence key={`detail-${scan.id}`}>
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
                borderBottom: "1px solid var(--border-subtle)",
                background: "rgba(28,28,46,0.03)",
              }}
            >
              <HistoryBrokenList scan={scan} />
            </td>
          </motion.tr>
        )}
      </AnimatePresence>,
    ];
  };

  // A collapsed run: "N scans with no change" + its time span, expanding to the
  // individual scans (each still its own clickable row).
  const runRows = (scans: ScanHistoryEntry[]) => {
    const runId = scans[0].id;
    const isOpen = expandedRuns.has(runId);
    const rows: React.ReactNode[] = [
      <tr
        key={`run-${runId}`}
        onClick={() => toggleRun(runId)}
        style={{
          cursor: "pointer",
          borderBottom: "1px solid var(--border-subtle)",
          background: "rgba(28,28,46,0.02)",
        }}
      >
        <td colSpan={5} style={{ padding: "10px 12px" }}>
          <div className="flex items-center justify-between">
            <span
              className="flex items-center gap-2"
              style={{ fontFamily: POPPINS, fontSize: "12px", color: "var(--text-muted)" }}
            >
              {isOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
              {scans.length} scans with no change
            </span>
            <span
              style={{
                fontFamily: POPPINS,
                fontSize: "11px",
                color: "var(--text-muted)",
                fontVariantNumeric: "tabular-nums",
                whiteSpace: "nowrap",
              }}
            >
              {runSpan(scans)}
            </span>
          </div>
        </td>
      </tr>,
    ];
    if (isOpen) {
      for (const s of scans) rows.push(...scanRow(s, true));
    }
    return rows;
  };

  return (
    <div>
      {/* Only-show-changes toggle (on by default): collapses runs of identical
          scans. Off renders every scan individually. */}
      <div className="flex items-center justify-end" style={{ marginBottom: 8 }}>
        <label
          className="flex items-center gap-2"
          style={{
            cursor: "pointer",
            userSelect: "none",
            fontFamily: POPPINS,
            fontSize: "11px",
            color: "var(--text-muted)",
          }}
        >
          <input
            type="checkbox"
            checked={onlyChanges}
            onChange={(e) => setOnlyChanges(e.target.checked)}
            style={{ accentColor: "var(--signal)", cursor: "pointer", width: 13, height: 13 }}
          />
          Only show changes
        </label>
      </div>

      {/* Health Score Chart — or, when the score never moves, a one-line note
          (a flat line across N identical points conveys nothing). */}
      <div style={{ marginBottom: 20, marginTop: 8 }}>
        {showChart ? (
          allSameScore ? (
            <div
              className="flex items-center gap-2"
              style={{
                padding: "12px 14px",
                borderRadius: 8,
                background: "rgba(79,70,229,0.06)",
                border: "1px solid rgba(79,70,229,0.12)",
              }}
            >
              <TrendingUp size={14} style={{ color: "var(--signal)" }} />
              <span style={{ fontFamily: POPPINS, fontSize: "12px", color: "var(--text-muted)" }}>
                Health score steady at {history[0].health_score} across{" "}
                {history.length} scans
              </span>
            </div>
          ) : (
            <div>
              <div
                className="flex items-center gap-2 mb-3"
                style={{ paddingLeft: 4 }}
              >
                <TrendingUp size={14} style={{ color: "var(--signal)" }} />
                <span
                  style={{
                    fontFamily: POPPINS,
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
                  margin={{ top: 8, right: 16, bottom: 4, left: -20 }}
                >
                  <XAxis
                    dataKey="date"
                    axisLine={false}
                    tickLine={false}
                    tick={{
                      fontSize: 10,
                      fill: "var(--text-muted)",
                      fontFamily: POPPINS,
                    }}
                  />
                  <YAxis
                    domain={[0, 100]}
                    axisLine={false}
                    tickLine={false}
                    tick={{
                      fontSize: 10,
                      fill: "var(--text-muted)",
                      fontFamily: POPPINS,
                    }}
                  />
                  <RechartsTooltip
                    content={<CustomChartTooltip />}
                    cursor={{ stroke: "rgba(79,70,229,0.2)" }}
                  />
                  <Line
                    type="monotone"
                    dataKey="score"
                    stroke="var(--signal)"
                    strokeWidth={2.5}
                    dot={{ fill: "var(--signal)", r: 4, strokeWidth: 0 }}
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
          )
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
            <TrendingUp size={14} style={{ color: "var(--signal)" }} />
            <span style={{ fontFamily: POPPINS, fontSize: "12px", color: "var(--text-muted)" }}>
              Scan again to see your health trend
            </span>
          </div>
        )}
      </div>

      {/* History Table */}
      <div className="overflow-x-auto" style={{ borderRadius: 8 }}>
        <table
          style={{ width: "100%", borderCollapse: "collapse", minWidth: 500 }}
        >
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
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
                    fontFamily: POPPINS,
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
            {onlyChanges
              ? items.map((item) =>
                  item.kind === "single"
                    ? scanRow(item.scan)
                    : runRows(item.scans)
                )
              : history.map((scan) => scanRow(scan))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
