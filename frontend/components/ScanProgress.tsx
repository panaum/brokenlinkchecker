"use client";

import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { X } from "lucide-react";

interface ScanProgressProps {
  message: string;
  percent: number;
  checkedCount?: number;
  totalCount?: number;
  feed?: string[];
  onCancel?: () => void;
}

// Color a streamed line by what it reports. We only have the real SSE progress
// messages (message + percent) — no per-link status codes are in the stream, so
// we don't invent them. Lines are colored by keyword where meaning is genuine.
function lineTone(line: string): string {
  const l = line.toLowerCase();
  if (l.includes("no pages") || l.includes("failed") || l.includes("error")) return "var(--status-broken)";
  if (l.includes("checked") || l.includes("complete") || l.includes("found")) return "var(--signal)";
  return "var(--text-secondary)";
}

export default function ScanProgress({
  message,
  percent,
  checkedCount,
  totalCount,
  feed = [],
  onCancel,
}: ScanProgressProps) {
  const feedRef = useRef<HTMLDivElement>(null);

  // Keep the newest streamed line in view.
  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: "smooth" });
  }, [feed.length]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.25, ease: [0.165, 0.84, 0.44, 1] }}
      className="ds-container"
      style={{ maxWidth: 720, padding: "0 24px", marginTop: 16 }}
    >
      <div className="ds-card" style={{ padding: "var(--space-6)", position: "relative", overflow: "hidden" }}>
        {/* soft signal glow behind the radar */}
        <div style={{ position: "absolute", top: -60, left: "50%", transform: "translateX(-50%)", width: 320, height: 320, borderRadius: "50%", background: "radial-gradient(circle, rgba(168,85,247,0.10), transparent 65%)", pointerEvents: "none" }} />

        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "var(--space-5)", position: "relative" }}>
          {/* ── RADAR ── */}
          <div style={{ position: "relative", width: 176, height: 176 }}>
            {/* concentric rings */}
            {[176, 128, 80, 36].map((d) => (
              <div key={d} style={{ position: "absolute", top: "50%", left: "50%", width: d, height: d, marginTop: -d / 2, marginLeft: -d / 2, borderRadius: "50%", border: "1px solid rgba(168,85,247,0.16)" }} />
            ))}
            {/* cross-hairs */}
            <div style={{ position: "absolute", top: "50%", left: 0, right: 0, height: 1, background: "rgba(168,85,247,0.12)" }} />
            <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "rgba(168,85,247,0.12)" }} />
            {/* sweep */}
            <div className="radar-sweep" />
            {/* activity blip — remounts on each new streamed line and replays. */}
            {feed.length > 0 && (
              <div
                key={feed.length}
                style={{
                  position: "absolute",
                  top: `${28 + (feed.length * 37) % 44}%`,
                  left: `${34 + (feed.length * 53) % 40}%`,
                  width: 10, height: 10, borderRadius: "50%",
                  background: "var(--signal)",
                  boxShadow: "0 0 10px var(--signal)",
                  animation: "radar-blip 900ms var(--ease-out-quart) forwards",
                }}
              />
            )}
            {/* center */}
            <div style={{ position: "absolute", top: "50%", left: "50%", width: 6, height: 6, marginTop: -3, marginLeft: -3, borderRadius: "50%", background: "var(--signal)", boxShadow: "0 0 8px var(--signal)" }} />
          </div>

          {/* counter — mono, tabular */}
          <div style={{ textAlign: "center" }}>
            <div className="font-mono" style={{ fontSize: 26, fontWeight: 600, color: "var(--text-primary)" }}>
              {checkedCount !== undefined && totalCount ? `${checkedCount} / ${totalCount}` : `${percent}%`}
            </div>
            <div className="font-mono" style={{ fontSize: 11, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase", marginTop: 2 }}>
              {totalCount ? "links checked" : "scanning"}
            </div>
          </div>

          {/* ── TERMINAL FEED ── the real SSE messages, streamed, not swallowed. */}
          <div
            ref={feedRef}
            className="font-mono"
            style={{
              width: "100%", height: 132, overflowY: "auto",
              background: "rgba(3,8,9,0.55)", border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-md)", padding: "10px 14px",
              fontSize: 12.5, lineHeight: 1.7,
            }}
          >
            {feed.length === 0 ? (
              <div style={{ color: "var(--text-muted)" }}>› initializing operation…</div>
            ) : (
              feed.map((line, i) => (
                <div key={i} style={{ color: lineTone(line), whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  <span style={{ color: "var(--text-muted)" }}>›</span> {line}
                </div>
              ))
            )}
            {/* live cursor line */}
            <div style={{ color: "var(--signal)" }}>
              <span style={{ color: "var(--text-muted)" }}>›</span> {message}
              <span style={{ opacity: 0.7 }}>▋</span>
            </div>
          </div>

          {onCancel && (
            <button
              onClick={onCancel}
              className="ds-btn-ghost"
              style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "7px 14px", fontSize: "var(--text-caption)" }}
            >
              <X size={13} /> Abort scan
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}
