"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ExternalLink, Globe } from "lucide-react";
import { ScanMeta } from "@/types";

interface PagePreviewCardProps {
  meta: ScanMeta;
  onRescan: () => void;
}

export default function PagePreviewCard({ meta, onRescan }: PagePreviewCardProps) {
  const [faviconError, setFaviconError] = useState(false);

  let origin = "";
  let displayUrl = meta.scannedUrl;
  let domain = meta.scannedUrl;

  try {
    const u = new URL(meta.scannedUrl);
    origin = u.origin;
    domain = u.hostname;
    displayUrl =
      meta.scannedUrl.length > 60
        ? meta.scannedUrl.slice(0, 60) + "…"
        : meta.scannedUrl;
  } catch {
    // fallback
  }

  const faviconUrl = origin ? `${origin}/favicon.ico` : "";
  const firstLetter = domain.replace("www.", "").charAt(0).toUpperCase();

  const now = new Date();
  const diffMs = now.getTime() - meta.scannedAt.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const timeLabel =
    diffSec < 10
      ? "just now"
      : `at ${meta.scannedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-5xl mx-auto mt-6 px-4"
      >
        <div className="glass-card px-5 py-4 flex items-center gap-4">
          {/* Favicon / fallback */}
          <div
            className="shrink-0 rounded-lg overflow-hidden flex items-center justify-center"
            style={{
              width: 36,
              height: 36,
              background:
                "linear-gradient(132deg,rgb(65,0,153),rgb(138,26,155))",
            }}
          >
            {faviconUrl && !faviconError ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={faviconUrl}
                alt="favicon"
                width={20}
                height={20}
                onError={() => setFaviconError(true)}
                className="object-contain"
              />
            ) : (
              <span
                style={{
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                  fontWeight: 700,
                  fontSize: "16px",
                  color: "#fff",
                }}
              >
                {firstLetter}
              </span>
            )}
          </div>

          {/* Info */}
          <div className="flex flex-col gap-0.5 flex-1 min-w-0">
            <span
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontWeight: 600,
                fontSize: "14px",
                color: "#fff",
              }}
            >
              {meta.pageTitle || domain}
            </span>
            <a
              href={meta.scannedUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 transition-opacity hover:opacity-80"
              style={{
                fontFamily: "monospace",
                fontSize: "12px",
                color: "rgba(255,255,255,0.4)",
              }}
            >
              <Globe size={11} />
              {displayUrl}
              <ExternalLink size={10} />
            </a>
          </div>

          {/* Timestamp */}
          <span
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontSize: "12px",
              color: "rgba(255,255,255,0.35)",
              whiteSpace: "nowrap",
            }}
          >
            Scanned {timeLabel}
          </span>

          {/* Re-scan button */}
          <button
            onClick={onRescan}
            className="shrink-0 px-3 py-1.5 rounded-lg transition-all cursor-pointer"
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontSize: "12px",
              fontWeight: 500,
              color: "rgba(255,255,255,0.6)",
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.12)",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background =
                "rgba(255,255,255,0.1)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background =
                "rgba(255,255,255,0.05)";
            }}
          >
            Re-scan
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
