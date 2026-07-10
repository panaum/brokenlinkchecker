"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Loader2, ShieldCheck, ShieldAlert, ServerCrash } from "lucide-react";

interface WatchdogHost {
  host: string;
  resource_type?: string | null;
  status?: number | null;
  down: boolean;
  affected_sites: number;
  sites: { site_id?: string; site_url?: string; client?: string }[];
}

interface WatchdogData {
  hosts?: WatchdogHost[];
  outages?: number;
  total_hosts?: number;
  error?: string;
}

// Every string below is derived from the API response. There is no invented
// status, time, or count — if we do not know something, we say so.
function siteWord(n: number): string {
  return n === 1 ? "site" : "sites";
}

export default function WatchdogPanel() {
  const [data, setData] = useState<WatchdogData | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/watchdog/hosts", { cache: "no-store" });
      setData(await res.json());
    } catch {
      setData({ error: "Could not reach the watchdog." });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm" style={{ color: "rgba(255,255,255,0.4)" }}>
        <Loader2 size={14} className="animate-spin" /> Loading third-party dependencies…
      </div>
    );
  }

  const hosts = data?.hosts ?? [];
  const outages = data?.outages ?? 0;

  // Nothing scanned yet is a real, distinct state — not "all healthy".
  if (!data?.error && hosts.length === 0) {
    return (
      <div
        className="rounded-xl p-4 text-sm"
        style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.5)" }}
      >
        <div className="flex items-center gap-2 mb-1" style={{ fontWeight: 600, color: "rgba(255,255,255,0.75)" }}>
          <ShieldCheck size={16} /> Third-party watchdog
        </div>
        No third-party dependencies recorded yet. Run a scan and the services your
        sites load will be listed here.
      </div>
    );
  }

  return (
    <div
      className="rounded-xl p-4"
      style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)" }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2" style={{ fontWeight: 600, fontSize: 14 }}>
          {outages > 0 ? (
            <ShieldAlert size={16} style={{ color: "#f87171" }} />
          ) : (
            <ShieldCheck size={16} style={{ color: "#4ade80" }} />
          )}
          Third-party watchdog
        </div>
        <span style={{ fontSize: 12, color: "rgba(255,255,255,0.5)" }}>
          {hosts.length} {hosts.length === 1 ? "service" : "services"}
          {outages > 0 && (
            <span style={{ color: "#f87171" }}> · {outages} down</span>
          )}
        </span>
      </div>

      {data?.error && (
        <div style={{ color: "#fca5a5", fontSize: 12, marginBottom: 8 }}>{data.error}</div>
      )}

      {/* One honest line per dependency. Down first (the API already sorts). */}
      <div className="flex flex-col">
        {hosts.map((h) => (
          <div
            key={h.host}
            className="flex items-center justify-between py-1.5"
            style={{ borderTop: "1px solid rgba(255,255,255,0.05)", fontSize: 13 }}
          >
            <div className="flex items-center gap-2 min-w-0">
              {h.down ? (
                <ServerCrash size={13} style={{ color: "#f87171", flexShrink: 0 }} />
              ) : (
                <span style={{ width: 7, height: 7, borderRadius: 999, background: "#4ade80", flexShrink: 0 }} />
              )}
              <span
                style={{ color: "rgba(255,255,255,0.85)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                title={h.host}
              >
                {h.host}
              </span>
            </div>
            <div className="flex items-center gap-3" style={{ flexShrink: 0 }}>
              <span style={{ color: "rgba(255,255,255,0.4)", fontSize: 12 }}>
                {h.affected_sites} {siteWord(h.affected_sites)}
              </span>
              {h.down ? (
                <span
                  style={{ color: "#fca5a5", fontSize: 11, fontWeight: 500 }}
                >
                  Outage{h.status ? ` · ${h.status}` : ""}
                </span>
              ) : (
                <span style={{ color: "rgba(74,222,128,0.8)", fontSize: 11 }}>Operational</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {outages > 0 && (
        <p style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", marginTop: 10, lineHeight: 1.5 }}>
          A service outage above breaks an embed on the affected sites — but it is
          the provider&apos;s outage, not a broken link on the client&apos;s site,
          so it never counts against their health score.
        </p>
      )}
    </div>
  );
}
