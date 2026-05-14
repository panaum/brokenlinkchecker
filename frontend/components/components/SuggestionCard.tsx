"use client";

import { useState, useRef, useEffect } from "react";
import { ExternalLink, Copy, Check, Lightbulb, AlertTriangle, HelpCircle } from "lucide-react";
import { LinkSuggestion } from "@/types";

interface SuggestionCardProps {
  suggestion: LinkSuggestion;
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

export default function SuggestionCard({ suggestion }: SuggestionCardProps) {
  const [copied, setCopied] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const hoverRef = useRef<HTMLAnchorElement>(null);

  const doCopy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  // Intent: intentionally_deleted
  if (suggestion.intent === "intentionally_deleted") {
    return (
      <div
        className="flex items-start gap-2 mt-2 rounded-lg px-3 py-3"
        style={{
          background: "rgba(248,113,113,0.06)",
          border: "1px solid rgba(248,113,113,0.25)",
        }}
      >
        <AlertTriangle size={14} style={{ color: "#f87171", marginTop: 2, flexShrink: 0 }} />
        <div>
          <span style={{ fontSize: "12px", color: "#f87171", fontFamily: "var(--font-poppins), Poppins, sans-serif", fontWeight: 600 }}>
            ⚠️ This page appears to have been deliberately removed. Do not replace.
          </span>
          {suggestion.wayback_last_seen && (
            <div style={{ fontSize: "11px", color: "rgba(255,255,255,0.35)", marginTop: 4, fontFamily: "var(--font-poppins), Poppins, sans-serif" }}>
              Last seen in Wayback Machine: {suggestion.wayback_last_seen}
            </div>
          )}
        </div>
      </div>
    );
  }

  // Intent: never_existed
  if (suggestion.intent === "never_existed" && !suggestion.suggested_url) {
    return (
      <div
        className="flex items-start gap-2 mt-2 rounded-lg px-3 py-3"
        style={{
          background: "rgba(251,191,36,0.06)",
          border: "1px solid rgba(251,191,36,0.2)",
        }}
      >
        <HelpCircle size={14} style={{ color: "#fbbf24", marginTop: 2, flexShrink: 0 }} />
        <span style={{ fontSize: "12px", color: "rgba(255,255,255,0.6)", fontFamily: "var(--font-poppins), Poppins, sans-serif" }}>
          This URL never existed — likely a typo when the link was created.
        </span>
      </div>
    );
  }

  // No suggestion URL or confidence too low
  if (!suggestion.suggested_url || suggestion.confidence < 60) {
    return null;
  }

  // Confidence-based border color
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
    <div
      className="mt-2 rounded-lg px-4 py-3"
      style={{
        background: "rgba(255,255,255,0.03)",
        border: `1px solid ${borderColor}40`,
        borderLeft: `3px solid ${borderColor}`,
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <Lightbulb size={14} style={{ color: borderColor }} />
        <span style={{ fontSize: "12px", fontWeight: 600, color: borderColor, fontFamily: "var(--font-poppins), Poppins, sans-serif" }}>
          Suggested Replacement
        </span>
        <span style={{ fontSize: "10px", color: "rgba(255,255,255,0.3)", fontFamily: "var(--font-poppins), Poppins, sans-serif", marginLeft: "auto" }}>
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
      <div className="flex items-center gap-3 mt-2">
        <span style={{ fontSize: "11px", color: "rgba(255,255,255,0.5)", fontFamily: "var(--font-poppins), Poppins, sans-serif" }}>
          Confidence: <strong style={{ color: borderColor }}>{suggestion.confidence}%</strong>
        </span>
      </div>
      <div style={{ fontSize: "11px", color: "rgba(255,255,255,0.4)", fontFamily: "var(--font-poppins), Poppins, sans-serif", marginTop: 4 }}>
        {suggestion.reasoning}
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-2 mt-3">
        <button
          onClick={(e) => { e.stopPropagation(); doCopy(suggestion.suggested_url!); }}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg cursor-pointer transition-colors"
          style={{
            background: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.1)",
            fontSize: "11px",
            color: "rgba(255,255,255,0.6)",
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
            fontWeight: 500,
          }}
        >
          {copied ? <Check size={12} style={{ color: "#4ade80" }} /> : <Copy size={12} />}
          {copied ? "Copied!" : "Copy URL"}
        </button>
        <a
          href={suggestion.suggested_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors"
          style={{
            background: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.1)",
            fontSize: "11px",
            color: "rgba(255,255,255,0.6)",
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
            fontWeight: 500,
            textDecoration: "none",
          }}
        >
          <ExternalLink size={12} />
          Open Page
        </a>
        {suggestion.can_auto_fix && (
          <button
            onClick={(e) => { e.stopPropagation(); doCopy(suggestion.suggested_url!); }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg cursor-pointer transition-colors"
            style={{
              background: "rgba(74,222,128,0.12)",
              border: "1px solid rgba(74,222,128,0.25)",
              fontSize: "11px",
              color: "#4ade80",
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontWeight: 600,
            }}
          >
            <Check size={12} />
            Use This Fix
          </button>
        )}
      </div>
    </div>
  );
}
