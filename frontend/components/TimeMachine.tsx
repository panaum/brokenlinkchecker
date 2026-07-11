"use client";

import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, ReferenceLine } from "recharts";
import { LinkResult } from "@/types";
import { findingKey, flaggedOf } from "@/lib/history";

interface Snapshot {
  id: string;
  scanned_at: string;
  health_score: number;
  broken_count: number;
  dead_cta_count: number;
  total_links: number;
  results_json: LinkResult[];
}

function scoreColor(s: number): string {
  if (s >= 90) return "var(--signal)";
  if (s >= 70) return "var(--status-attention)";
  return "var(--status-broken)";
}
function bucketCls(r: LinkResult): string {
  const b = r.bucket ?? (r.label === "broken" ? "broken" : r.label === "dead_cta" ? "dead_cta" : "unverifiable");
  return b === "broken" ? "ds-status-broken" : b === "dead_cta" ? "ds-status-attention" : "ds-status-neutral";
}

// A scrubber across every snapshot of a site. Drag (or ← →) to move through
// time: the score marker follows the thumb and the findings list below appears
// / resolves accordingly. Read-only; data is the existing scan history.
export default function TimeMachine({ siteUrl }: { siteUrl: string }) {
  const [snaps, setSnaps] = useState<Snapshot[] | null>(null);
  const [idx, setIdx] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`/api/history?url=${encodeURIComponent(siteUrl)}`)
      .then((r) => (r.ok ? r.json() : { history: [] }))
      .then((d) => {
        // Backend returns newest-first; the timeline reads oldest -> newest.
        const asc: Snapshot[] = [...(d.history ?? [])].sort(
          (a, b) => new Date(a.scanned_at).getTime() - new Date(b.scanned_at).getTime(),
        );
        setSnaps(asc);
        setIdx(Math.max(0, asc.length - 1));
      })
      .catch(() => setSnaps([]));
  }, [siteUrl]);

  const chartData = useMemo(
    () => (snaps ?? []).map((s, i) => ({ i, score: s.health_score })),
    [snaps],
  );

  const step = useCallback((delta: number) => {
    setIdx((i) => Math.min((snaps?.length ?? 1) - 1, Math.max(0, i + delta)));
  }, [snaps]);

  // ← → step snapshots when the scrubber has focus.
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
    else if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
  };

  if (snaps === null) {
    return <div className="ds-card ds-card-pad"><div className="ds-skeleton" style={{ height: 200 }} /></div>;
  }
  if (snaps.length < 2) {
    return (
      <div className="ds-card ds-card-pad ds-text-secondary" style={{ fontSize: "var(--text-body)" }}>
        Not enough history yet — the time machine needs at least two scans.
      </div>
    );
  }

  const cur = snaps[idx];
  const prev = idx > 0 ? snaps[idx - 1] : null;
  const curFlagged = flaggedOf(cur.results_json);
  const prevKeys = new Set(flaggedOf(prev?.results_json).map(findingKey));
  const curKeys = new Set(curFlagged.map(findingKey));
  const newCount = curFlagged.filter((r) => !prevKeys.has(findingKey(r))).length;
  const resolvedCount = prev ? [...prevKeys].filter((k) => !curKeys.has(k)).length : 0;
  const scoreDelta = prev ? cur.health_score - prev.health_score : 0;

  return (
    <div
      ref={rootRef}
      className="ds-card ds-card-pad"
      tabIndex={0}
      onKeyDown={onKeyDown}
      style={{ outline: "none", display: "flex", flexDirection: "column", gap: "var(--space-4)" }}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div className="font-mono ds-text-secondary" style={{ fontSize: 12 }}>
            {new Date(cur.scanned_at).toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginTop: 2 }}>
            <span className="font-mono" style={{ fontSize: 30, fontWeight: 700, color: scoreColor(cur.health_score) }}>{cur.health_score}</span>
            {prev && (
              <span className="font-mono" style={{ fontSize: 13, color: scoreDelta > 0 ? "var(--signal)" : scoreDelta < 0 ? "var(--status-broken)" : "var(--text-muted)" }}>
                {scoreDelta > 0 ? `▲ +${scoreDelta}` : scoreDelta < 0 ? `▼ ${scoreDelta}` : "no change"}
              </span>
            )}
          </div>
        </div>
        <div className="font-mono ds-text-muted" style={{ fontSize: 12, textAlign: "right" }}>
          snapshot {idx + 1} / {snaps.length}
          {prev && (
            <div style={{ marginTop: 2 }}>
              {resolvedCount > 0 && <span style={{ color: "var(--signal)" }}>{resolvedCount} resolved</span>}
              {resolvedCount > 0 && newCount > 0 && " · "}
              {newCount > 0 && <span style={{ color: "var(--status-broken)" }}>{newCount} new</span>}
            </div>
          )}
        </div>
      </div>

      {/* Score line with a marker that follows the thumb. */}
      <div style={{ height: 120, marginLeft: -8 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <XAxis dataKey="i" hide />
            <YAxis domain={[0, 100]} width={28} tick={{ fill: "var(--text-muted)", fontSize: 11 }} axisLine={false} tickLine={false} />
            <Line type="monotone" dataKey="score" stroke="var(--signal)" strokeWidth={2} dot={false} isAnimationActive={false} />
            <ReferenceLine x={idx} stroke="var(--text-secondary)" strokeDasharray="3 3" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Scrubber */}
      <input
        type="range"
        min={0}
        max={snaps.length - 1}
        value={idx}
        onChange={(e) => setIdx(Number(e.target.value))}
        aria-label="Scrub through scan history"
        style={{ width: "100%", accentColor: "var(--signal)" }}
      />

      {/* Findings at this point in time */}
      <div>
        <div className="font-mono ds-text-muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
          {curFlagged.length} finding{curFlagged.length === 1 ? "" : "s"} at this snapshot
        </div>
        {curFlagged.length === 0 ? (
          <p className="ds-status ds-status-healthy" style={{ fontSize: "var(--text-body)" }}><span className="ds-status-dot" />All clear.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 260, overflowY: "auto" }}>
            {curFlagged.map((r, i) => {
              const isNew = !prevKeys.has(findingKey(r));
              return (
                <div key={findingKey(r) + i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", borderRadius: "var(--radius-sm)", background: isNew ? "rgba(255,107,107,0.06)" : "transparent" }}>
                  <span className={`ds-status ${bucketCls(r)}`} style={{ flexShrink: 0 }}><span className="ds-status-dot" /></span>
                  <span className="ds-text-primary" style={{ fontSize: "var(--text-caption)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", flexShrink: 1, minWidth: 0 }}>
                    {r.anchor_text || "(no anchor)"}
                  </span>
                  <span className="ds-text-muted font-mono" style={{ fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", flex: 1, minWidth: 0 }}>{r.url}</span>
                  {isNew && <span className="font-mono" style={{ fontSize: 10, color: "var(--status-broken)", flexShrink: 0 }}>NEW</span>}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
