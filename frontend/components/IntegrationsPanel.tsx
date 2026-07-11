"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { Puzzle, Check, X, Clock, HelpCircle, Loader2, ChevronDown } from "lucide-react";

interface Integration {
  host: string;
  resource_url: string;
  category: string;
  type: string;
  detected_id?: string | null;
  health_status: string;
  last_checked_at?: string | null;
}

const STATUS: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  healthy: { icon: <Check size={13} />, color: "#4ade80", label: "Healthy" },
  down: { icon: <X size={13} />, color: "#f87171", label: "Down" },
  unresponsive: { icon: <Clock size={13} />, color: "#fbbf24", label: "Unresponsive" },
  unknown: { icon: <HelpCircle size={13} />, color: "#94a3b8", label: "Unknown" },
  checking: { icon: <Loader2 size={13} className="animate-spin" />, color: "#94a3b8", label: "Checking…" },
};

function relTime(iso?: string | null): string {
  if (!iso) return "";
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (Number.isNaN(mins)) return "";
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  return `${Math.floor(mins / 60)}h ago`;
}

export default function IntegrationsPanel({ scanId, pageUrl }: { scanId: string; pageUrl: string }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Integration[] | null>(null);
  const [loading, setLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(
        `/api/scans/${scanId}/integrations?page=${encodeURIComponent(pageUrl)}`,
        { cache: "no-store" },
      );
      const body = await res.json();
      setData(body.integrations ?? []);
      // Poll while any resource is still "checking".
      const pending = (body.integrations ?? []).some((i: Integration) => i.health_status === "checking");
      if (pending) {
        pollRef.current = setTimeout(load, 2500);
      }
    } catch {
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [scanId, pageUrl]);

  // Fetch the count once on mount (so the badge shows without opening).
  useEffect(() => {
    setLoading(true);
    load();
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [load]);

  // Escape closes; focus returns to the button.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        btnRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const count = data?.length ?? 0;
  const downCount = (data ?? []).filter((i) => i.health_status === "down").length;

  // Hidden entirely when there are no third-party integrations.
  if (!loading && count === 0) return null;

  // Group by category for the panel.
  const byCategory: Record<string, Integration[]> = {};
  for (const i of data ?? []) (byCategory[i.category] ??= []).push(i);

  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <button
        ref={btnRef}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => { if (e.key === "Enter") setOpen((o) => !o); }}
        aria-expanded={open}
        aria-haspopup="true"
        className="inline-flex items-center gap-1.5 cursor-pointer"
        style={{
          padding: "4px 10px", borderRadius: 8, fontSize: 12, fontWeight: 500,
          border: `1px solid ${downCount ? "rgba(248,113,113,0.4)" : "rgba(255,255,255,0.12)"}`,
          background: downCount ? "rgba(248,113,113,0.08)" : "rgba(255,255,255,0.04)",
          color: downCount ? "#fca5a5" : "rgba(255,255,255,0.75)",
        }}
      >
        <Puzzle size={13} />
        Integrations
        <span
          style={{
            minWidth: 18, textAlign: "center", padding: "0 5px", borderRadius: 999, fontSize: 11,
            background: downCount ? "#f87171" : "rgba(255,255,255,0.12)",
            color: downCount ? "#fff" : "rgba(255,255,255,0.8)",
          }}
        >
          {loading && data === null ? "…" : count}
        </span>
        <ChevronDown size={12} style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform .15s" }} />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Third-party integrations on this page"
          style={{
            position: "absolute", zIndex: 40, top: "calc(100% + 6px)", right: 0,
            width: 380, maxHeight: 440, overflowY: "auto",
            background: "#12101a", border: "1px solid rgba(255,255,255,0.12)",
            borderRadius: 12, padding: 14, boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>
            Third-party tools on this page ({count})
          </div>

          {downCount > 0 && (
            <div
              className="rounded-lg px-3 py-2 mb-3"
              style={{ background: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.3)", fontSize: 11.5, color: "#fca5a5", lineHeight: 1.5 }}
            >
              A tool below isn&apos;t loading — its feature (booking, chat, tracking) is likely broken for visitors.
            </div>
          )}

          {Object.entries(byCategory).map(([cat, items]) => (
            <div key={cat} style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.06em", color: "rgba(255,255,255,0.4)", marginBottom: 5 }}>
                {cat}
              </div>
              {items.map((i, idx) => {
                const s = STATUS[i.health_status] ?? STATUS.unknown;
                return (
                  <div key={i.resource_url + idx} className="flex items-center justify-between py-1" style={{ fontSize: 12.5 }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ color: "rgba(255,255,255,0.9)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={i.resource_url}>
                        {i.host}
                        {i.detected_id && (
                          <span style={{ color: "rgba(255,255,255,0.4)", marginLeft: 6, fontSize: 11 }}>{i.detected_id}</span>
                        )}
                      </div>
                      <div style={{ color: "rgba(255,255,255,0.35)", fontSize: 10.5 }}>
                        {i.type}{i.last_checked_at ? ` · checked ${relTime(i.last_checked_at)}` : ""}
                      </div>
                    </div>
                    <div
                      className="flex items-center gap-1"
                      style={{ color: s.color, fontSize: 11, flexShrink: 0 }}
                      title={i.health_status === "unknown"
                        ? "This provider blocks automated checks — status can't be verified. This does not mean it's broken."
                        : s.label}
                    >
                      {s.icon} {s.label}
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
