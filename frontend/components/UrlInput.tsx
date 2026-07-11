"use client";

import { useState, useEffect } from "react";
import { Search } from "lucide-react";

interface UrlInputProps {
  url: string;
  onUrlChange: (url: string) => void;
  onScan: () => void;
  scanning: boolean;
  error: string | null;
  scanMode?: "single" | "site";
  onScanModeChange?: (mode: "single" | "site") => void;
}

function isValidUrl(value: string): boolean {
  try {
    const u = new URL(value);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

function getSuggestion(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) return null;
  // Looks like a domain
  if (trimmed.includes(".") && !trimmed.includes(" ")) {
    return `https://${trimmed}`;
  }
  return null;
}

export default function UrlInput({
  url,
  onUrlChange,
  onScan,
  scanning,
  error,
  scanMode = "single",
  onScanModeChange,
}: UrlInputProps) {
  const [dots, setDots] = useState("");
  const [inlineError, setInlineError] = useState<string | null>(null);
  const suggestion = getSuggestion(url);

  // Animate scanning dots
  useEffect(() => {
    if (!scanning) { setDots(""); return; }
    const id = setInterval(() => {
      setDots((d) => (d.length >= 3 ? "" : d + "."));
    }, 400);
    return () => clearInterval(id);
  }, [scanning]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !scanning) handleScan();
  };

  const handleScan = () => {
    const trimmed = url.trim();
    if (!trimmed) {
      setInlineError("Please enter a URL to scan.");
      return;
    }
    const autoUrl =
      !trimmed.startsWith("http://") && !trimmed.startsWith("https://")
        ? "https://" + trimmed
        : trimmed;
    if (!isValidUrl(autoUrl)) {
      setInlineError("Please enter a valid URL starting with https:// or http://");
      return;
    }
    setInlineError(null);
    if (autoUrl !== url) onUrlChange(autoUrl);
    onScan();
  };

  const displayError = inlineError || error;

  return (
    <div className="w-full max-w-3xl mx-auto mt-10">
      <div className="animated-border glass-card p-6">
        {/* Scan Mode Tabs */}
        {onScanModeChange && (
          <div className="flex justify-start gap-2 mb-4">
            <button
              type="button"
              disabled={scanning}
              onClick={() => onScanModeChange("single")}
              className={`px-4 py-2 rounded-lg text-xs sm:text-sm font-medium transition-all cursor-pointer ${
                scanMode === "single"
                  ? "border"
                  : "text-white/60 hover:text-white/80 hover:bg-white/5 border border-transparent"
              }`}
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                ...(scanMode === "single"
                  ? { background: "rgba(34,211,170,0.14)", color: "var(--signal)", borderColor: "rgba(34,211,170,0.4)" }
                  : {}),
              }}
            >
              Single Page
            </button>
            <button
              type="button"
              disabled={scanning}
              onClick={() => onScanModeChange("site")}
              className={`px-4 py-2 rounded-lg text-xs sm:text-sm font-medium transition-all cursor-pointer ${
                scanMode === "site"
                  ? "border"
                  : "text-white/60 hover:text-white/80 hover:bg-white/5 border border-transparent"
              }`}
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                ...(scanMode === "site"
                  ? { background: "rgba(34,211,170,0.14)", color: "var(--signal)", borderColor: "rgba(34,211,170,0.4)" }
                  : {}),
              }}
            >
              Full Website (Sitemap/Crawl)
            </button>
          </div>
        )}

        <div className="flex flex-col sm:flex-row gap-3">
          <input
            id="url-input"
            type="text"
            autoFocus
            value={url}
            onChange={(e) => {
              onUrlChange(e.target.value);
              setInlineError(null);
            }}
            onKeyDown={handleKeyDown}
            placeholder="https://your-website.com"
            className="font-mono flex-1 rounded-xl px-5 py-4 outline-none transition-all"
            style={{
              fontFamily: "var(--font-stack-mono)",
              fontSize: 14,
              background: "rgba(3,8,9,0.5)",
              color: "var(--text-primary)",
              border: "1px solid var(--border-subtle)",
            }}
            onFocus={(e) => { e.currentTarget.style.borderColor = "var(--signal)"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(34,211,170,0.18)"; }}
            onBlur={(e) => { e.currentTarget.style.borderColor = "var(--border-subtle)"; e.currentTarget.style.boxShadow = "none"; }}
            disabled={scanning}
          />
          <button
            id="scan-button"
            onClick={handleScan}
            disabled={scanning}
            className="ds-btn-primary flex items-center justify-center gap-2 whitespace-nowrap"
            style={{
              padding: "0 32px",
              minWidth: "140px",
            }}
          >
            {scanning ? (
              <span>Scanning{dots}</span>
            ) : (
              <>
                <Search size={18} />
                {scanMode === "site" ? "Scan Website" : "Scan Page"}
              </>
            )}
          </button>
        </div>

        {/* Suggestion */}
        {suggestion && !scanning && (
          <div
            className="mt-3 text-sm flex items-center gap-2"
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              color: "rgba(255,255,255,0.5)",
            }}
          >
            Did you mean&nbsp;
            <button
              onClick={() => { onUrlChange(suggestion); setInlineError(null); }}
              className="font-mono underline cursor-pointer transition-colors"
              style={{ color: "var(--signal)" }}
            >
              {suggestion}
            </button>
            ?
          </div>
        )}

        {/* Inline error */}
        {displayError && (
          <div
            className="mt-3 text-sm flex items-start gap-2"
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              color: "#f87171",
            }}
          >
            <span>⚠</span>
            <span>{displayError}</span>
          </div>
        )}
      </div>
    </div>
  );
}
