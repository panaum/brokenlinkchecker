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

const CADENCE_SECONDS: Record<string, number> = {
  hourly: 3600,
  daily: 86400,
  weekly: 604800,
};

// The scheduler fires on an interval, not at a wall-clock time. The next check
// is roughly the last one plus the cadence — never an invented "9:00 AM".
function nextCheck(lastIso?: string | null, freq?: string): string {
  const interval = CADENCE_SECONDS[(freq || "daily").toLowerCase()] ?? 86400;
  const base = lastIso ? new Date(lastIso).getTime() : Date.now();
  const dueMs = (Number.isNaN(base) ? Date.now() : base) + interval * 1000;
  const mins = Math.round((dueMs - Date.now()) / 60000);
  if (mins <= 0) return "due now";
  if (mins < 60) return `~in ${mins}m`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `~in ${hrs}h`;
  return `~in ${Math.round(hrs / 24)}d`;
}

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
  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState<string | null>(null);

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

  const runCheckNow = async () => {
    setChecking(true);
    setCheckResult(null);
    try {
      const res = await fetch(`/api/sites/${siteId}/monitoring/run-now`, {
        method: "POST",
      });
      const body = await res.json();
      setCheckResult(body.explanation || body.error || "Check complete.");
      await load(); // "last checked" should have advanced — proof it ran
    } catch {
      setCheckResult("Could not reach the server.");
    } finally {
      setChecking(false);
    }
  };

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
      <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
        <Loader2 size={14} className="animate-spin" /> Loading monitoring…
      </div>
    );
  }

  const enabled = Boolean(status?.monitoring_enabled);
  const streak = status?.healthy_streak_days;

  return (
    <div
      className="rounded-xl p-4"
      style={{ background: "var(--surface-card)", border: "1px solid var(--border-subtle)" }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Activity size={16} style={{ color: enabled ? "#4caf7d" : "var(--text-muted)" }} />
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
            borderColor: enabled ? "rgba(76,175,125,0.4)" : "var(--border-strong)",
            background: enabled ? "rgba(76,175,125,0.12)" : "transparent",
            color: enabled ? "#4caf7d" : "var(--text-secondary)",
          }}
        >
          {saving ? "…" : enabled ? "On" : "Off"}
        </button>
      </div>

      {error && (
        <div
          className="mb-3 rounded-lg px-3 py-2"
          style={{
            background: "rgba(224,92,92,0.1)",
            border: "1px solid rgba(224,92,92,0.3)",
            color: "var(--status-broken)",
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
                border: "1px solid var(--border-subtle)",
                background: status?.freq === c ? "rgba(91,141,239,0.15)" : "transparent",
                color: status?.freq === c ? "#5b8def" : "var(--text-muted)",
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
          style={{ color: "#4caf7d", fontSize: 13, fontWeight: 500 }}
        >
          <ShieldCheck size={14} />
          Healthy {streak} {streak === 1 ? "day" : "days"}
        </div>
      )}

      <div className="grid grid-cols-2 gap-y-1 text-xs" style={{ color: "var(--text-muted)" }}>
        <span>Last checked</span>
        <span style={{ textAlign: "right", color: "var(--text-primary)" }}>
          {timeAgo(status?.last_checked)}
        </span>
        {enabled && (
          <>
            <span>Next check</span>
            <span style={{ textAlign: "right", color: "var(--text-primary)" }}>
              {nextCheck(status?.last_checked, status?.freq)}
            </span>
          </>
        )}
        <span>Current health</span>
        <span style={{ textAlign: "right", color: "var(--text-primary)" }}>
          {status?.current_health ?? "—"}
          {status?.current_health != null ? "/100" : ""}
        </span>
        {status?.digest && (
          <>
            <span>This week</span>
            <span style={{ textAlign: "right", color: "var(--text-primary)" }}>
              {status.digest.checks} checks · {status.digest.issues_caught} caught ·{" "}
              {status.digest.issues_resolved} resolved
            </span>
          </>
        )}
      </div>

      {status?.recent_events && status.recent_events.length > 0 && (
        <div className="mt-3 pt-3" style={{ borderTop: "1px solid var(--border-subtle)" }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>
            Recent changes
          </div>
          {status.recent_events.slice(0, 5).map((e, i) => (
            <div key={i} className="flex items-center justify-between" style={{ fontSize: 12, padding: "2px 0" }}>
              <span style={{ color: "var(--text-secondary)" }}>{timeAgo(e.at)}</span>
              <span>
                {e.new > 0 && <span style={{ color: "#e05c5c" }}>+{e.new} broke </span>}
                {e.fixed > 0 && <span style={{ color: "#4caf7d" }}>{e.fixed} fixed</span>}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Verify it works without waiting for the cadence: this runs the exact
          scheduled-check path once and reports what it decided. */}
      {enabled && (
        <div className="mt-3 pt-3" style={{ borderTop: "1px solid var(--border-subtle)" }}>
          <button
            onClick={runCheckNow}
            disabled={checking}
            className="cursor-pointer w-full"
            style={{
              padding: "6px 12px",
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 500,
              border: "1px solid rgba(91,141,239,0.3)",
              background: "rgba(91,141,239,0.1)",
              color: "#5b8def",
            }}
          >
            {checking ? "Running a check…" : "Run a check now"}
          </button>
          {checkResult && (
            <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 8, lineHeight: 1.5 }}>
              {checkResult}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
