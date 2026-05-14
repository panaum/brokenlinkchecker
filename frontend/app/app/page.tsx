"use client";

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { AnimatePresence } from "framer-motion";
import { LinkResult, FilterType, SortOption, ScanMeta } from "@/types";
import UrlInput from "@/components/UrlInput";
import ScanProgress from "@/components/ScanProgress";
import StatsBar from "@/components/StatsBar";
import FilterBar from "@/components/FilterBar";
import ResultsTable from "@/components/ResultsTable";
import HealthScore from "@/components/HealthScore";
import SummaryBanner from "@/components/SummaryBanner";
import PagePreviewCard from "@/components/PagePreviewCard";

// ─── Health score calculator (mirrored from HealthScore component) ─────────────
function calcScore(results: LinkResult[]): number {
  if (results.length === 0) return 100;
  const total = results.length;
  const okCount = results.filter((r) => r.label === "ok").length;
  const brokenCount = results.filter((r) => r.label === "broken").length;
  const deadCtaCount = results.filter((r) => r.label === "dead_cta").length;
  const timeoutCount = results.filter((r) => r.label === "timeout").length;
  let score = Math.round((okCount / total) * 100);
  score -= brokenCount * 3;
  score -= deadCtaCount * 2;
  score -= timeoutCount * 1;
  return Math.max(0, Math.min(100, score));
}

// ─── Particle dot background ─────────────────────────────────────────────────
function ParticleBg() {
  return (
    <svg
      aria-hidden="true"
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        zIndex: 0,
        opacity: 0.35,
      }}
    >
      <defs>
        <pattern
          id="dots"
          x="0"
          y="0"
          width="40"
          height="40"
          patternUnits="userSpaceOnUse"
        >
          <circle cx="1.5" cy="1.5" r="1.5" fill="rgba(138,26,155,0.5)" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#dots)" />
    </svg>
  );
}

export default function HomePage() {
  const [url, setUrl] = useState("");
  const [scanning, setScanning] = useState(false);
  const [progress, setProgress] = useState({ message: "", percent: 0 });
  const [checkedCount, setCheckedCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [results, setResults] = useState<LinkResult[]>([]);
  const [filter, setFilter] = useState<FilterType>("all");
  const [sortOption, setSortOption] = useState<SortOption>("status");
  const [search, setSearch] = useState("");
  const [zoneFilter, setZoneFilter] = useState("All zones");
  const [error, setError] = useState<string | null>(null);
  const [scanComplete, setScanComplete] = useState(false);
  const [scanMeta, setScanMeta] = useState<ScanMeta | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const scanningRef = useRef(false);

  // Dynamic page title
  useEffect(() => {
    if (scanning) {
      document.title = "Scanning… | LinkSpy";
    } else if (scanComplete && results.length > 0) {
      const issues = results.filter((r) => r.label !== "ok").length;
      document.title = `${issues} issue${issues !== 1 ? "s" : ""} found | LinkSpy`;
    } else {
      document.title = "LinkSpy — Broken Link Checker";
    }
  }, [scanning, scanComplete, results]);

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  const cancelScan = useCallback(() => {
    eventSourceRef.current?.close();
    setScanning(false);
    scanningRef.current = false;
    setProgress({ message: "Scan cancelled.", percent: 0 });
  }, []);

  const startScan = useCallback(
    (overrideUrl?: string) => {
      const scanUrl = overrideUrl ?? url.trim();
      if (!scanUrl) return;

      // Reset state
      setError(null);
      setResults([]);
      setScanComplete(false);
      setScanning(true);
      scanningRef.current = true;
      setProgress({ message: "Initializing scan…", percent: 0 });
      setFilter("all");
      setSearch("");
      setZoneFilter("All zones");
      setCheckedCount(0);
      setTotalCount(0);

      // Close any existing connection
      eventSourceRef.current?.close();

      const es = new EventSource(`/api/scan?url=${encodeURIComponent(scanUrl)}`);
      eventSourceRef.current = es;

      es.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data as string);

          if (data.type === "progress") {
            setProgress({ message: data.message as string, percent: data.percent as number });

            // Parse checked/total out of messages like "Checked 5 of 32 links"
            const match = (data.message as string).match(/(\d+)\s+of\s+(\d+)/);
            if (match) {
              setCheckedCount(parseInt(match[1], 10));
              setTotalCount(parseInt(match[2], 10));
            }
          } else if (data.type === "result") {
            const linkResults = data.data as LinkResult[];
            setResults(linkResults);
            setScanComplete(true);
            setScanning(false);
            scanningRef.current = false;
            setProgress({ message: "Scan complete!", percent: 100 });
            setScanMeta({
              scannedUrl: scanUrl,
              scannedAt: new Date(),
            });
            es.close();
          } else if (data.type === "error") {
            setError(data.message as string);
            setScanning(false);
            scanningRef.current = false;
            es.close();
          }
        } catch {
          // Ignore parse errors from keep-alive or empty messages
        }
      };

      es.onerror = () => {
        if (scanningRef.current) {
          setError(
            "Connection to server failed. Make sure the backend is running on port 8000."
          );
          setScanning(false);
          scanningRef.current = false;
        }
        es.close();
      };
    },
    [url]
  );

  // ─── Filtering ─────────────────────────────────────────────────────────────
  const filteredResults = useMemo(() => {
    let list = results;

    // Status filter
    if (filter !== "all") {
      if (filter === "blocked") {
        list = list.filter(
          (r) => r.label === "blocked" || r.label === "forbidden"
        );
      } else {
        list = list.filter((r) => r.label === filter || r.category === filter);
      }
    }

    // Zone filter
    if (zoneFilter !== "All zones") {
      list = list.filter((r) => r.category === zoneFilter);
    }

    // Search filter
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(
        (r) =>
          r.url.toLowerCase().includes(q) ||
          r.anchor_text.toLowerCase().includes(q)
      );
    }

    return list;
  }, [results, filter, zoneFilter, search]);

  const healthScore = useMemo(() => calcScore(results), [results]);

  const handleRescan = useCallback(() => {
    if (scanMeta) startScan(scanMeta.scannedUrl);
  }, [scanMeta, startScan]);

  return (
    <main className="min-h-screen relative overflow-hidden">
      {/* ── HERO SECTION ── */}
      <section className="relative pt-20 pb-8 noise-overlay overflow-hidden">
        {/* Particle dot background */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 0,
            overflow: "hidden",
          }}
        >
          <ParticleBg />
        </div>

        {/* Decorative gradient orbs */}
        <div
          className="absolute top-[-200px] left-[-200px] w-[600px] h-[600px] rounded-full bg-gradient-1 opacity-30 pointer-events-none"
          style={{ filter: "blur(120px)", zIndex: 1 }}
        />
        <div
          className="absolute top-[-100px] right-[-150px] w-[400px] h-[400px] rounded-full bg-gradient-3 opacity-20 pointer-events-none"
          style={{ filter: "blur(120px)", zIndex: 1 }}
        />

        {/* Hero content */}
        <div className="relative z-10 text-center px-4">
          {/* Badge pill */}
          <div className="inline-flex items-center gap-2 bg-gradient-2 px-4 py-2 rounded-full mb-6">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse-dot" />
            <span
              className="text-white/90 text-sm"
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontWeight: 500,
              }}
            >
              Link Auditor
            </span>
          </div>

          {/* H1 */}
          <h1
            className="text-4xl sm:text-5xl lg:text-[56px] leading-tight mb-4"
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontWeight: 700,
            }}
          >
            Find Every{" "}
            <span className="gradient-text">Broken Link</span>
          </h1>

          {/* Subtitle */}
          <p
            className="max-w-2xl mx-auto text-lg"
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontWeight: 400,
              color: "rgba(255,255,255,0.60)",
              fontSize: "18px",
            }}
          >
            Paste any URL below — we crawl every nav link, footer, CTA, header
            and body text link and report what&apos;s broken.
          </p>
        </div>
      </section>

      {/* ── URL INPUT ── */}
      <section className="relative z-10 px-4">
        <UrlInput
          url={url}
          onUrlChange={setUrl}
          onScan={startScan}
          scanning={scanning}
          error={error}
        />
      </section>

      {/* ── PROGRESS ── */}
      <section className="relative z-10 px-4">
        <AnimatePresence>
          {scanning && (
            <ScanProgress
              message={progress.message}
              percent={progress.percent}
              checkedCount={checkedCount}
              totalCount={totalCount}
              onCancel={cancelScan}
            />
          )}
        </AnimatePresence>
      </section>

      {/* ── POST-SCAN RESULTS ── */}
      {scanComplete && results.length > 0 && (
        <>
          {/* Page preview card */}
          {scanMeta && (
            <PagePreviewCard meta={scanMeta} onRescan={handleRescan} />
          )}

          {/* Health score */}
          <section className="relative z-10">
            <HealthScore results={results} />
          </section>

          {/* Summary banner */}
          <section className="relative z-10">
            <SummaryBanner results={results} />
          </section>

          {/* Stats bar */}
          <section className="relative z-10">
            <StatsBar results={results} />
          </section>

          {/* Filter bar */}
          <section className="relative z-10">
            <FilterBar
              results={results}
              filter={filter}
              onFilterChange={setFilter}
              sortOption={sortOption}
              onSortChange={setSortOption}
              search={search}
              onSearchChange={setSearch}
              zoneFilter={zoneFilter}
              onZoneFilterChange={setZoneFilter}
              filteredCount={filteredResults.length}
            />
          </section>

          {/* Results table */}
          <section className="relative z-10 pb-20">
            <ResultsTable
              results={filteredResults}
              sortOption={sortOption}
              scannedUrl={scanMeta?.scannedUrl ?? url}
              healthScore={healthScore}
            />
          </section>
        </>
      )}

      {/* ── ZERO LINKS EDGE CASE ── */}
      {scanComplete && results.length === 0 && (
        <section className="relative z-10 px-4 mt-10">
          <div className="w-full max-w-3xl mx-auto glass-card p-10 text-center flex flex-col items-center gap-5">
            <svg width="72" height="72" viewBox="0 0 72 72" fill="none">
              <circle cx="36" cy="36" r="32" stroke="rgba(255,255,255,0.08)" strokeWidth="2" />
              <path d="M24 36h24M36 24v24" stroke="rgba(255,255,255,0.15)" strokeWidth="2" strokeLinecap="round" />
              <circle cx="36" cy="36" r="8" stroke="rgba(255,255,255,0.1)" strokeWidth="2" />
            </svg>
            <div>
              <p
                style={{
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                  fontWeight: 600,
                  fontSize: "18px",
                  color: "rgba(255,255,255,0.7)",
                  marginBottom: 8,
                }}
              >
                We couldn&apos;t find any links on this page
              </p>
              <ul
                style={{
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                  fontWeight: 400,
                  fontSize: "14px",
                  color: "rgba(255,255,255,0.4)",
                  lineHeight: 2,
                  listStyle: "none",
                  padding: 0,
                }}
              >
                <li>• The page may require login</li>
                <li>• JavaScript may have failed to load</li>
                <li>• The URL may be incorrect</li>
              </ul>
            </div>
            <button
              onClick={() => startScan()}
              className="bg-gradient-1 text-white rounded-xl px-6 py-3 cursor-pointer hover:opacity-90 transition-opacity"
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontWeight: 600,
                fontSize: "14px",
              }}
            >
              Try Again
            </button>
          </div>
        </section>
      )}
    </main>
  );
}
