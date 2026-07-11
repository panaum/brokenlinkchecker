"use client";

import React, { useState } from "react";
import { Copy, Check } from "lucide-react";
import { middleTruncateUrl, relativeTime, absoluteTime, latencyColor, copyRich, urlSegmentDiff } from "@/lib/format";

// ── MiddleTruncate ──────────────────────────────────────────────────────────
// A URL shown middle-truncated (domain + last segment always visible), in mono,
// with the full URL as a tooltip and one-click copy.
export function MiddleTruncate({ url, max, className, style }: { url: string; max?: number; className?: string; style?: React.CSSProperties }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    if (await copyRich(url)) {
      setCopied(true);
      setTimeout(() => setCopied(false), 800);
    }
  };
  return (
    <button
      type="button"
      onClick={onCopy}
      title={copied ? "Copied" : url}
      className={`font-mono ${className ?? ""}`}
      style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "none", border: "none", padding: 0, cursor: "pointer", color: "inherit", maxWidth: "100%", minWidth: 0, ...style }}
    >
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>
        {middleTruncateUrl(url, max)}
      </span>
      {copied ? <Check size={12} style={{ color: "var(--signal)", flexShrink: 0 }} /> : <Copy size={12} style={{ opacity: 0.4, flexShrink: 0 }} />}
    </button>
  );
}

// ── RelativeTime ────────────────────────────────────────────────────────────
// "2h ago" with the absolute timestamp on hover.
export function RelativeTime({ iso, className, style }: { iso: string | number | Date; className?: string; style?: React.CSSProperties }) {
  return (
    <span title={absoluteTime(iso)} className={className} style={style}>
      {relativeTime(iso)}
    </span>
  );
}

// ── Latency ─────────────────────────────────────────────────────────────────
// Response time in mono, tinted green/amber/red by threshold.
export function Latency({ ms, style }: { ms: number | null | undefined; style?: React.CSSProperties }) {
  if (ms == null) return null;
  return (
    <span className="font-mono" style={{ color: latencyColor(ms), fontSize: 11, ...style }}>
      {Math.round(ms)}ms
    </span>
  );
}

// ── Delta ───────────────────────────────────────────────────────────────────
// A signed, semantically-colored change. For issue metrics a DECREASE is good
// (green); for health metrics an INCREASE is good. Fixed-width, tabular.
export function Delta({ value, kind, suffix, style }: { value: number; kind: "issue" | "health"; suffix?: string; style?: React.CSSProperties }) {
  if (value === 0) {
    return <span className="font-mono ds-text-muted" style={style}>±0{suffix}</span>;
  }
  const good = kind === "issue" ? value < 0 : value > 0;
  const color = good ? "var(--signal)" : "var(--status-broken)";
  const sign = value > 0 ? "+" : "";
  return (
    <span className="font-mono" style={{ color, ...style }}>
      {sign}{value}{suffix}
    </span>
  );
}

// ── UrlDiff ─────────────────────────────────────────────────────────────────
// A fix suggestion: shared prefix, the OLD segment struck through, the NEW
// segment signal-colored, shared suffix. Never two full URLs side by side.
export function UrlDiff({ oldUrl, newUrl, style }: { oldUrl: string; newUrl: string; style?: React.CSSProperties }) {
  const { prefix, oldMid, newMid, suffix } = urlSegmentDiff(oldUrl, newUrl);
  return (
    <span className="font-mono" style={{ fontSize: 12, wordBreak: "break-all", ...style }}>
      <span className="ds-text-secondary">{prefix}</span>
      {oldMid && <span style={{ color: "var(--status-broken)", textDecoration: "line-through", opacity: 0.8 }}>{oldMid}</span>}
      {oldMid && newMid ? <span className="ds-text-muted"> → </span> : null}
      {newMid && <span style={{ color: "var(--signal)" }}>{newMid}</span>}
      <span className="ds-text-secondary">{suffix}</span>
    </span>
  );
}

// ── CopyButton ──────────────────────────────────────────────────────────────
// Rich clipboard (text/html + text/plain); icon morphs to a check for 800ms.
export function CopyButton({ text, html, label, className, style }: { text: string; html?: string; label?: string; className?: string; style?: React.CSSProperties }) {
  const [copied, setCopied] = useState(false);
  const onClick = async () => {
    if (await copyRich(text, html)) {
      setCopied(true);
      setTimeout(() => setCopied(false), 800);
    }
  };
  return (
    <button type="button" onClick={onClick} className={className} style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer", ...style }}>
      {copied ? <Check size={14} style={{ color: "var(--signal)" }} /> : <Copy size={14} />}
      {label && <span>{copied ? "Copied" : label}</span>}
    </button>
  );
}
