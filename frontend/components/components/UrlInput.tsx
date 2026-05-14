"use client";

import { useState, useEffect } from "react";
import { Search } from "lucide-react";

interface UrlInputProps {
  url: string;
  onUrlChange: (url: string) => void;
  onScan: () => void;
  scanning: boolean;
  error: string | null;
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
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            id="url-input"
            type="text"
            value={url}
            onChange={(e) => {
              onUrlChange(e.target.value);
              setInlineError(null);
            }}
            onKeyDown={handleKeyDown}
            placeholder="https://your-website.com"
            className="flex-1 bg-black/30 text-white placeholder-white/30 rounded-xl px-5 py-4 border border-white/10 focus:border-purple-500 focus:ring-2 focus:ring-purple-500/30 outline-none transition-all"
            style={{ fontFamily: "var(--font-poppins), Poppins, sans-serif" }}
            disabled={scanning}
          />
          <button
            id="scan-button"
            onClick={handleScan}
            disabled={scanning}
            className="bg-gradient-1 text-white font-semibold rounded-xl px-8 py-4 hover:opacity-90 disabled:opacity-60 transition-all flex items-center justify-center gap-2 cursor-pointer whitespace-nowrap"
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontWeight: 600,
              minWidth: "140px",
            }}
          >
            {scanning ? (
              <span>Scanning{dots}</span>
            ) : (
              <>
                <Search size={18} />
                Scan Page
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
              className="underline cursor-pointer transition-colors hover:text-white"
              style={{ color: "#a78bfa" }}
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
