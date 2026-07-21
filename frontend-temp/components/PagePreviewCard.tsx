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
            className="shrink-0 rounded-lg overflow-hidden flex items-center justify-center bg-accent"
            style={{ width: 36, height: 36 }}
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
                className="text-text-on-dark"
                style={{ fontWeight: 700, fontSize: "16px" }}
              >
                {firstLetter}
              </span>
            )}
          </div>

          {/* Info */}
          <div className="flex flex-col gap-0.5 flex-1 min-w-0">
            <span
              className="text-text-primary"
              style={{ fontWeight: 600, fontSize: "14px" }}
            >
              {meta.pageTitle || domain}
            </span>
            <a
              href={meta.scannedUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-text-secondary transition-colors hover:text-accent"
              style={{ fontFamily: "monospace", fontSize: "12px" }}
            >
              <Globe size={11} />
              {displayUrl}
              <ExternalLink size={10} />
            </a>
          </div>

          {/* Timestamp */}
          <span
            className="text-text-muted"
            style={{ fontSize: "12px", whiteSpace: "nowrap" }}
          >
            Scanned {timeLabel}
          </span>

          {/* Re-scan button */}
          <button
            onClick={onRescan}
            className="shrink-0 px-3 py-1.5 rounded-lg transition-colors cursor-pointer text-text-secondary hover:bg-card-soft hover:text-text-primary"
            style={{
              fontSize: "12px",
              fontWeight: 500,
              background: "var(--color-card)",
              border: "1px solid var(--color-border-soft)",
            }}
          >
            Re-scan
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
