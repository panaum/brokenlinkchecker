"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Activity, Loader2, ShieldCheck } from "lucide-react";

interface MonitoringStatus {
  monitored?: boolean;
  monitoring_enabled?: boolean;
  freq?: string;
  last_checked?: string | null;
  current_health?: number | null;
  healthy_streak_days?: number | null;
  open_findings?: number;
  recent_events?: { at: string; new: number; fixed: number; health_score?: number }[];
  digest?: {
    checks: number;
    issues_caught: number;
    issues_resolved: number;
  };
}

const CADENCES = ["hourly", "daily", "weekly"];

function timeAgo(iso?: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "never";
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function MonitoringPanel({ siteId }: { siteId: string }) {
  const [status, setStatus] = useState<MonitoringStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/sites/${siteId}/monitoring`, { cache: "no-store" });
      setStatus(await res.json());
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    load();
  }, [load]);

  const update = async (enabled: boolean, freq?: string) => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/sites/${siteId}/monitoring`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled, freq: freq ?? status?.freq ?? "daily" }),
      });
      // A failed save must not silently revert the toggle to off. Say why.
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.error || `Could not save (HTTP ${res.status}).`);
        return;
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not reach the server.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm" style={{ color: "rgba(255,255,255,0.4)" }}>
        <Loader2 size={14} className="animate-spin" /> Loading monitoring…
      </div>
    );
  }

  const enabled = Boolean(status?.monitoring_enabled);
  const streak = status?.healthy_streak_days;

  return (
    <div
      className="rounded-xl p-4"
      style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)" }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Activity size={16} style={{ color: enabled ? "#4ade80" : "rgba(255,255,255,0.4)" }} />
          <span style={{ fontWeight: 600, fontSize: 14 }}>Monitoring</span>
        </div>
        <button
          onClick={() => update(!enabled)}
          disabled={saving}
          className="cursor-pointer"
          style={{
            padding: "4px 12px",
            borderRadius: 999,
            fontSize: 12,
            fontWeight: 500,
            border: "1px solid",
            borderColor: enabled ? "rgba(74,222,128,0.4)" : "rgba(255,255,255,0.15)",
            background: enabled ? "rgba(74,222,128,0.12)" : "transparent",
            color: enabled ? "#4ade80" : "rgba(255,255,255,0.6)",
          }}
        >
          {saving ? "…" : enabled ? "On" : "Off"}
        </button>
      </div>

      {error && (
        <div
          className="mb-3 rounded-lg px-3 py-2"
          style={{
            background: "rgba(248,113,113,0.1)",
            border: "1px solid rgba(248,113,113,0.3)",
            color: "#fca5a5",
            fontSize: 12,
            lineHeight: 1.4,
          }}
        >
          {error}
        </div>
      )}

      {enabled && (
        <div className="flex items-center gap-2 mb-3">
          {CADENCES.map((c) => (
            <button
              key={c}
              onClick={() => update(true, c)}
              disabled={saving}
              className="cursor-pointer"
              style={{
                padding: "2px 10px",
                borderRadius: 6,
                fontSize: 11,
                textTransform: "capitalize",
                border: "1px solid rgba(255,255,255,0.1)",
                background: status?.freq === c ? "rgba(96,165,250,0.15)" : "transparent",
                color: status?.freq === c ? "#60a5fa" : "rgba(255,255,255,0.5)",
              }}
            >
              {c}
            </button>
          ))}
        </div>
      )}

      {/* The uptime record — the sellable artifact. */}
      {typeof streak === "number" && streak > 0 && (
        <div
          className="flex items-center gap-2 mb-2"
          style={{ color: "#4ade80", fontSize: 13, fontWeight: 500 }}
        >
          <ShieldCheck size={14} />
          Healthy {streak} {streak === 1 ? "day" : "days"}
        </div>
      )}

      <div className="grid grid-cols-2 gap-y-1 text-xs" style={{ color: "rgba(255,255,255,0.55)" }}>
        <span>Last checked</span>
        <span style={{ textAlign: "right", color: "rgba(255,255,255,0.8)" }}>
          {timeAgo(status?.last_checked)}
        </span>
        <span>Current health</span>
        <span style={{ textAlign: "right", color: "rgba(255,255,255,0.8)" }}>
          {status?.current_health ?? "—"}
          {status?.current_health != null ? "/100" : ""}
        </span>
        {status?.digest && (
          <>
            <span>This week</span>
            <span style={{ textAlign: "right", color: "rgba(255,255,255,0.8)" }}>
              {status.digest.checks} checks · {status.digest.issues_caught} caught ·{" "}
              {status.digest.issues_resolved} resolved
            </span>
          </>
        )}
      </div>

      {status?.recent_events && status.recent_events.length > 0 && (
        <div className="mt-3 pt-3" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
          <div style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", marginBottom: 6 }}>
            Recent changes
          </div>
          {status.recent_events.slice(0, 5).map((e, i) => (
            <div key={i} className="flex items-center justify-between" style={{ fontSize: 12, padding: "2px 0" }}>
              <span style={{ color: "rgba(255,255,255,0.7)" }}>{timeAgo(e.at)}</span>
              <span>
                {e.new > 0 && <span style={{ color: "#f87171" }}>+{e.new} broke </span>}
                {e.fixed > 0 && <span style={{ color: "#4ade80" }}>{e.fixed} fixed</span>}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
