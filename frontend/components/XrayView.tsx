"use client";

import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { LinkResult, XrayCapture, XrayElement } from "@/types";

// Bucket → signal color. broken = red, dead CTA = amber, everything else neutral.
function bucketColor(r: LinkResult): string {
  const b = r.bucket ?? (r.label === "broken" ? "broken" : r.label === "dead_cta" ? "dead_cta" : "unverifiable");
  if (b === "broken") return "var(--status-broken)";
  if (b === "dead_cta") return "var(--status-attention)";
  return "var(--status-neutral)";
}

function normUrl(u: string): string {
  try {
    const x = new URL(u);
    return (x.origin + x.pathname).replace(/\/+$/, "").toLowerCase();
  } catch {
    return (u || "").replace(/\/+$/, "").toLowerCase();
  }
}

interface Marker {
  fp: string;
  result: LinkResult;
  el: XrayElement;
  color: string;
}

export default function XrayView({
  results,
  pageUrl,
  fetcher,
}: {
  results: LinkResult[];
  pageUrl: string;
  // Injectable for tests / public report (defaults to the same-origin proxy).
  fetcher?: (url: string) => Promise<XrayCapture>;
}) {
  const [capture, setCapture] = useState<XrayCapture | null>(null);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const imgWrapRef = useRef<HTMLDivElement>(null);
  const [renderW, setRenderW] = useState(0);

  const flagged = useMemo(() => results.filter((r) => r.label !== "ok"), [results]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const get =
        fetcher ??
        (async (u: string) => {
          const res = await fetch(`/api/xray?url=${encodeURIComponent(u)}`, { cache: "no-store" });
          return (await res.json()) as XrayCapture;
        });
      setCapture(await get(pageUrl));
    } catch {
      setCapture({ available: false, error: "capture failed" });
    } finally {
      setLoading(false);
    }
  }, [pageUrl, fetcher]);

  useEffect(() => {
    load();
  }, [load]);

  // Track the rendered image width so markers scale with it.
  useEffect(() => {
    if (!imgWrapRef.current) return;
    const ro = new ResizeObserver((entries) => setRenderW(entries[0].contentRect.width));
    ro.observe(imgWrapRef.current);
    return () => ro.disconnect();
  }, [capture]);

  const pageW = capture?.page_width || capture?.viewport_width || 1280;
  const scale = renderW && pageW ? renderW / pageW : 0;

  // Match each flagged finding to a captured element (URL first, then text).
  const markers: Marker[] = useMemo(() => {
    const els = capture?.elements ?? [];
    if (!els.length) return [];
    const byUrl = new Map<string, XrayElement>();
    for (const e of els) if (e.url) byUrl.set(normUrl(e.url), e);
    const out: Marker[] = [];
    const usedText = new Set<XrayElement>();
    for (const r of flagged) {
      let el = r.url ? byUrl.get(normUrl(r.url)) : undefined;
      if (!el && r.anchor_text) {
        el = els.find((e) => !usedText.has(e) && e.text && e.text.trim() === r.anchor_text.trim());
        if (el) usedText.add(el);
      }
      if (el) out.push({ fp: r.fingerprint || r.url, result: r, el, color: bucketColor(r) });
    }
    return out;
  }, [capture, flagged]);

  const matchedFps = useMemo(() => new Set(markers.map((m) => m.fp)), [markers]);
  const unplaced = flagged.filter((r) => !matchedFps.has(r.fingerprint || r.url));

  // Pan the screenshot to a marker and flag it active (pulse).
  const focusMarker = useCallback((m: Marker) => {
    setActive(m.fp);
    if (scrollRef.current && scale) {
      const targetY = m.el.y * scale - scrollRef.current.clientHeight / 2 + (m.el.h * scale) / 2;
      scrollRef.current.scrollTo({ top: Math.max(0, targetY), behavior: "smooth" });
    }
  }, [scale]);

  if (loading) {
    return (
      <div className="ds-card ds-card-pad" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="ds-skeleton" style={{ height: 18, width: "30%" }} />
        <div className="ds-skeleton" style={{ height: 320, width: "100%" }} />
      </div>
    );
  }

  // Graceful degradation — capture unavailable: findings still list normally.
  if (!capture?.available || !capture.screenshot) {
    return (
      <div className="ds-card ds-card-pad">
        <div className="ds-text-secondary" style={{ fontSize: "var(--text-body)" }}>
          X-ray couldn&apos;t capture this page right now — the findings below are unaffected.
        </div>
      </div>
    );
  }

  return (
    <div className="ds-card ds-card-pad" style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 300px", gap: "var(--space-4)" }}>
      {/* Screenshot + markers */}
      <div ref={scrollRef} style={{ maxHeight: 560, overflowY: "auto", borderRadius: "var(--radius-md)", border: "1px solid var(--border-subtle)", background: "#000" }}>
        <div ref={imgWrapRef} style={{ position: "relative", width: "100%" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`data:image/png;base64,${capture.screenshot}`}
            alt="Captured page"
            style={{ display: "block", width: "100%", height: "auto" }}
          />
          {scale > 0 && markers.map((m) => {
            const isActive = active === m.fp;
            return (
              <button
                key={m.fp}
                onClick={() => focusMarker(m)}
                title={`${m.result.anchor_text || m.result.url}`}
                aria-label={`Finding: ${m.result.anchor_text || m.result.url}`}
                style={{
                  position: "absolute",
                  left: m.el.x * scale,
                  top: m.el.y * scale,
                  width: Math.max(10, m.el.w * scale),
                  height: Math.max(10, m.el.h * scale),
                  border: `2px solid ${m.color}`,
                  borderRadius: 4,
                  background: isActive ? "color-mix(in srgb, currentColor 18%, transparent)" : "transparent",
                  color: m.color,
                  boxShadow: isActive ? `0 0 0 3px color-mix(in srgb, ${"currentColor"} 30%, transparent)` : "none",
                  cursor: "pointer",
                  padding: 0,
                  animation: isActive ? "radar-blip 900ms var(--ease-out-quart)" : "none",
                }}
              />
            );
          })}
        </div>
      </div>

      {/* Findings rail */}
      <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 560, overflowY: "auto" }}>
        <div className="ds-text-muted font-mono" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
          {markers.length} located · {unplaced.length} unplaced
        </div>
        {markers.map((m) => (
          <div
            key={m.fp}
            onMouseEnter={() => focusMarker(m)}
            onClick={() => focusMarker(m)}
            style={{
              display: "flex", alignItems: "flex-start", gap: 8, padding: "8px 10px", borderRadius: "var(--radius-sm)",
              cursor: "pointer",
              background: active === m.fp ? "rgba(34,211,170,0.08)" : "transparent",
              border: `1px solid ${active === m.fp ? "var(--border-strong)" : "transparent"}`,
            }}
          >
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: m.color, marginTop: 5, flexShrink: 0 }} />
            <div style={{ minWidth: 0 }}>
              <div className="ds-text-primary" style={{ fontSize: "var(--text-caption)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {m.result.anchor_text || "(no anchor text)"}
              </div>
              <div className="ds-text-muted font-mono" style={{ fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {m.result.url}
              </div>
            </div>
          </div>
        ))}
        {unplaced.length > 0 && (
          <div className="ds-text-muted" style={{ fontSize: "var(--text-caption)", marginTop: 8, lineHeight: 1.5 }}>
            {unplaced.length} finding{unplaced.length === 1 ? "" : "s"} not on the page (meta tags, form actions, or off-screen) — see the full list below.
          </div>
        )}
      </div>
    </div>
  );
}
