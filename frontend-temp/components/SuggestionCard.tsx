"use client";

import { useState, useRef, useEffect } from "react";
import { ExternalLink, Copy, Check, Lightbulb, AlertTriangle, HelpCircle, Search, Trash2 } from "lucide-react";
import { motion } from "framer-motion";
import { LinkSuggestion } from "@/types";

interface SuggestionCardProps {
  suggestion: LinkSuggestion;
  url?: string;
}

function PreviewTooltip({ url }: { url: string }) {
  const [img, setImg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    fetch(`/api/preview?url=${encodeURIComponent(url)}`)
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled && data.screenshot) setImg(data.screenshot);
        else if (!cancelled) setError(true);
      })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [url]);

  return (
    <div
      style={{
        width: 280,
        background: "rgba(15,8,30,0.97)",
        border: "1px solid rgba(255,255,255,0.15)",
        borderRadius: 12,
        overflow: "hidden",
        boxShadow: "0 12px 40px rgba(0,0,0,0.6)",
        animation: "fadeIn 0.2s ease",
      }}
    >
      <div
        style={{
          padding: "6px 10px",
          fontSize: "10px",
          color: "rgba(255,255,255,0.4)",
          fontFamily: "var(--font-poppins), Poppins, sans-serif",
          fontWeight: 500,
          borderBottom: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        Preview
      </div>
      {loading && (
        <div style={{ padding: 20, textAlign: "center", color: "rgba(255,255,255,0.3)", fontSize: 12 }}>
          Loading preview…
        </div>
      )}
      {error && (
        <div style={{ padding: 20, textAlign: "center", color: "rgba(255,255,255,0.3)", fontSize: 12 }}>
          Preview unavailable
        </div>
      )}
      {img && (
        <img
          src={`data:image/png;base64,${img}`}
          alt="Page preview"
          style={{ width: "100%", display: "block" }}
        />
      )}
    </div>
  );
}

/* ─── Shared card wrapper with glass styling + framer-motion ─────────────── */
function GlassCard({
  borderColor,
  children,
}: {
  borderColor: string;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.2 }}
      style={{
        background: "rgba(255,255,255,0.04)",
        borderRadius: 8,
        padding: "12px 14px",
        marginTop: 8,
        borderLeft: `3px solid ${borderColor}`,
      }}
    >
      {children}
    </motion.div>
  );
}

/* ─── Shared button style ────────────────────────────────────────────────── */
const btnBase: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  padding: "6px 12px",
  borderRadius: 8,
  cursor: "pointer",
  background: "rgba(255,255,255,0.06)",
  border: "1px solid rgba(255,255,255,0.1)",
  fontSize: "11px",
  color: "rgba(255,255,255,0.6)",
  fontFamily: "var(--font-poppins), Poppins, sans-serif",
  fontWeight: 500,
  textDecoration: "none",
  transition: "background 0.15s ease",
};

const fontPoppins = "var(--font-poppins), Poppins, sans-serif";

export default function SuggestionCard({ suggestion, url }: SuggestionCardProps) {
  const [copied, setCopied] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [ctaInput, setCtaInput] = useState("");
  const [ctaCopied, setCtaCopied] = useState(false);
  const hoverRef = useRef<HTMLAnchorElement>(null);

  const doCopy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const doCopyCtaTemplate = async () => {
    const toCopy = ctaInput.trim() || "https://example.com/page";
    await navigator.clipboard.writeText(toCopy);
    setCtaCopied(true);
    setTimeout(() => setCtaCopied(false), 1500);
  };

  // ─── TYPE 2: Dead CTA ────────────────────────────────────────────────────
  if (suggestion.intent === "dead_cta") {
    return (
      <div
        className="mt-2 rounded-lg px-4 py-3"
        style={{
          background: "rgba(251,191,36,0.04)",
          borderLeft: "3px solid #fbbf24",
          border: "1px solid rgba(251,191,36,0.15)",
          borderRadius: "8px",
        }}
      >
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle size={14} style={{ color: "#fbbf24" }} />
          <span
            style={{
              fontSize: "12px",
              fontWeight: 600,
              color: "#fbbf24",
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
            }}
          >
            Dead Button Detected
          </span>
        </div>
        <div
          style={{
            fontSize: "11px",
            color: "rgba(255,255,255,0.5)",
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
            lineHeight: 1.5,
          }}
        >
          {suggestion.reasoning}
        </div>
      </div>
    );
  }

  // ─── TYPE 3: Blocked ─────────────────────────────────────────────────────
  if (suggestion.intent === "blocked") {
    return (
      <div
        className="mt-2 rounded-lg px-4 py-3"
        style={{
          background: "rgba(232,121,249,0.04)",
          borderLeft: "3px solid #e879f9",
          border: "1px solid rgba(232,121,249,0.15)",
          borderRadius: "8px",
        }}
      >
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle size={14} style={{ color: "#e879f9" }} />
          <span
            style={{
              fontSize: "12px",
              fontWeight: 600,
              color: "#e879f9",
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
            }}
          >
            Manual Verification Required
          </span>
        </div>
        <div
          style={{
            fontSize: "11px",
            color: "rgba(255,255,255,0.5)",
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
            lineHeight: 1.5,
          }}
        >
          {suggestion.reasoning}
        </div>
        <div className="flex items-center gap-2 mt-3">
          <a
            href={suggestion.suggested_url || "#"}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg"
            style={{
              background: "rgba(232,121,249,0.12)",
              border: "1px solid rgba(232,121,249,0.25)",
              fontSize: "11px",
              color: "#e879f9",
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontWeight: 500,
              textDecoration: "none",
            }}
          >
            <ExternalLink size={12} />
            Open in browser
          </a>
        </div>
      </div>
    );
  }

  // ─── TYPE 4: Intentionally Deleted ────────────────────────────────────────
  if (suggestion.intent === "intentionally_deleted") {
    return (
      <GlassCard borderColor="#f87171">
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <Trash2 size={14} style={{ color: "#f87171", flexShrink: 0 }} />
          <span
            style={{
              fontSize: "12px",
              fontWeight: 600,
              color: "#f87171",
              fontFamily: fontPoppins,
            }}
          >
            🗑️ Page Was Removed
          </span>
        </div>
        <div
          style={{
            fontSize: "12px",
            color: "rgba(255,255,255,0.6)",
            fontFamily: fontPoppins,
            lineHeight: 1.5,
          }}
        >
          This page was deliberately deleted (HTTP 410).
          <br />
          Do not replace — remove this link instead.
        </div>
        {suggestion.wayback_last_seen && (
          <div
            style={{
              fontSize: "11px",
              color: "rgba(255,255,255,0.35)",
              marginTop: 8,
              fontFamily: fontPoppins,
            }}
          >
            Last seen in Wayback Machine: {suggestion.wayback_last_seen}
          </div>
        )}
      </GlassCard>
    );
  }

  // ─── TYPE 5: Never Existed ────────────────────────────────────────────────
  if (suggestion.intent === "never_existed" && !suggestion.suggested_url) {
    return (
      <GlassCard borderColor="#94a3b8">
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <HelpCircle size={14} style={{ color: "#94a3b8", flexShrink: 0 }} />
          <span
            style={{
              fontSize: "12px",
              fontWeight: 600,
              color: "#94a3b8",
              fontFamily: fontPoppins,
            }}
          >
            ❓ URL Never Existed
          </span>
        </div>
        <div
          style={{
            fontSize: "12px",
            color: "rgba(255,255,255,0.6)",
            fontFamily: fontPoppins,
            lineHeight: 1.5,
          }}
        >
          This URL was never a real page.
          <br />
          It was likely a typo when the link was created.
          <br />
          Check the URL spelling carefully.
        </div>
      </GlassCard>
    );
  }

  // ─── No suggestion URL or confidence too low ─────────────────────────────
  if (!suggestion.suggested_url || suggestion.confidence < 60) {
    return null;
  }

  // ─── TYPE 1: Broken Link with suggested replacement ──────────────────────
  let borderColor = "#fbbf24"; // 60-69 yellow
  let borderLabel = "Use with caution";
  if (suggestion.confidence >= 90) {
    borderColor = "#4ade80"; // green
    borderLabel = "Auto-fix ready";
  } else if (suggestion.confidence >= 70) {
    borderColor = "#fb923c"; // orange
    borderLabel = "Review recommended";
  }

  return (
    <GlassCard borderColor={borderColor}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <Lightbulb size={14} style={{ color: borderColor }} />
        <span
          style={{
            fontSize: "12px",
            fontWeight: 600,
            color: borderColor,
            fontFamily: fontPoppins,
          }}
        >
          💡 Suggested Replacement
        </span>
        <span
          style={{
            fontSize: "10px",
            color: "rgba(255,255,255,0.3)",
            fontFamily: fontPoppins,
            marginLeft: "auto",
          }}
        >
          {borderLabel}
        </span>
      </div>

      {/* Suggested URL with hover preview */}
      <div style={{ position: "relative", display: "inline-block" }}>
        <a
          ref={hoverRef}
          href={suggestion.suggested_url}
          target="_blank"
          rel="noopener noreferrer"
          onMouseEnter={() => setShowPreview(true)}
          onMouseLeave={() => setShowPreview(false)}
          style={{
            fontFamily: "monospace",
            fontSize: "12px",
            color: borderColor,
            wordBreak: "break-all",
            textDecoration: "underline",
            textDecorationColor: `${borderColor}40`,
          }}
        >
          {suggestion.suggested_url}
        </a>
        {showPreview && (
          <div style={{ position: "absolute", bottom: "100%", left: 0, marginBottom: 8, zIndex: 100 }}>
            <PreviewTooltip url={suggestion.suggested_url} />
          </div>
        )}
      </div>

      {/* Confidence + reasoning */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 8 }}>
        <span style={{ fontSize: "11px", color: "rgba(255,255,255,0.5)", fontFamily: fontPoppins }}>
          Confidence: <strong style={{ color: borderColor }}>{suggestion.confidence}%</strong>
        </span>
      </div>
      <div style={{ fontSize: "11px", color: "rgba(255,255,255,0.4)", fontFamily: fontPoppins, marginTop: 4 }}>
        {suggestion.reasoning}
      </div>

      {/* Action buttons */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
        <button
          onClick={(e) => { e.stopPropagation(); doCopy(suggestion.suggested_url!); }}
          style={btnBase}
        >
          {copied ? <Check size={12} style={{ color: "#4ade80" }} /> : <Copy size={12} />}
          {copied ? "Copied!" : "Copy URL"}
        </button>
        <a
          href={suggestion.suggested_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          style={btnBase}
        >
          <ExternalLink size={12} />
          Open Page
        </a>
        {suggestion.can_auto_fix && (
          <button
            onClick={(e) => { e.stopPropagation(); doCopy(suggestion.suggested_url!); }}
            style={{
              ...btnBase,
              background: "rgba(74,222,128,0.12)",
              border: "1px solid rgba(74,222,128,0.25)",
              color: "#4ade80",
              fontWeight: 600,
            }}
          >
            <Check size={12} />
            Use This Fix
          </button>
        )}
      </div>
    </GlassCard>
  );
}
