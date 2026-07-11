"use client";

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { useSession } from "next-auth/react";
import { AnimatePresence } from "framer-motion";
import { LinkResult, FilterType, SortOption, ScanMeta, ScanDiff, DiffFilter, ResourceType, HostCount, RedirectSummary } from "@/types";
import UrlInput from "@/components/UrlInput";
import ScanProgress from "@/components/ScanProgress";
import StatsBar from "@/components/StatsBar";
import ReportHeader from "@/components/ReportHeader";
import IssueSections from "@/components/IssueSections";
import ResourcePanels from "@/components/ResourcePanels";
import ScanHistoryPanel from "@/components/ScanHistoryPanel";
import FilterBar from "@/components/FilterBar";
import ResultsTable from "@/components/ResultsTable";
import HealthScore from "@/components/HealthScore";
import SummaryBanner from "@/components/SummaryBanner";
import PagePreviewCard from "@/components/PagePreviewCard";
import WhatChangedCard from "@/components/WhatChangedCard";
import TrackingBanner from "@/components/TrackingBanner";
import NavBar from "@/components/NavBar";
import IntegrationsPanel from "@/components/IntegrationsPanel";
import Link from "next/link";
import { Wrench } from "lucide-react";

// ─── History scan entry type ──────────────────────────────────────────────────
interface HistoryScanEntry {
  id: string;
  scanned_at: string;
  total_links: number;
  broken_count: number;
  dead_cta_count: number;
  health_score: number;
  results_json: LinkResult[];
}

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
  const { data: session, status: sessionStatus } = useSession();
  const [url, setUrl] = useState("");
  const [scanning, setScanning] = useState(false);
  const [progress, setProgress] = useState({ message: "", percent: 0 });
  const [checkedCount, setCheckedCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [results, setResults] = useState<LinkResult[]>([]);
  const [detectedBuilders, setDetectedBuilders] = useState<string[]>([]);
  const [diff, setDiff] = useState<ScanDiff | null>(null);
  const [linkTypes, setLinkTypes] = useState<Partial<Record<ResourceType, number>>>({});
  const [topHosts, setTopHosts] = useState<HostCount[]>([]);
  const [schemes, setSchemes] = useState<Record<string, number>>({});
  const [redirects, setRedirects] = useState<RedirectSummary | null>(null);
  const [siteId, setSiteId] = useState<string | null>(null);
  const [diffFilter, setDiffFilter] = useState<DiffFilter>("all");
  const [filter, setFilter] = useState<FilterType>("all");
  const [sortOption, setSortOption] = useState<SortOption>("status");
  const [search, setSearch] = useState("");
  const [zoneFilter, setZoneFilter] = useState("All zones");
  const [error, setError] = useState<string | null>(null);
  const [scanComplete, setScanComplete] = useState(false);
  const [scanMeta, setScanMeta] = useState<ScanMeta | null>(null);
  const [scanId, setScanId] = useState<string | null>(null);
  const [scanMode, setScanMode] = useState<"single" | "site">("single");
  const eventSourceRef = useRef<EventSource | null>(null);
  const scanningRef = useRef(false);

  // ─── History state ─────────────────────────────────────────────────────────
  const [history, setHistory] = useState<HistoryScanEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const historyPanelRef = useRef<HTMLElement>(null);

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
      setDetectedBuilders([]);
      setDiff(null);
      setDiffFilter("all");
      setLinkTypes({});
      setTopHosts([]);
      setSchemes({});
      setRedirects(null);
      setSiteId(null);
      setScanComplete(false);
      setScanning(true);
      scanningRef.current = true;
      setProgress({ message: "Initializing scan…", percent: 0 });
      setFilter("all");
      setSearch("");
      setZoneFilter("All zones");
      setCheckedCount(0);
      setTotalCount(0);
      setHistory([]);
      setHistoryLoading(false);

      // Close any existing connection
      eventSourceRef.current?.close();

      // Connect the SSE stream directly to the backend when its public URL is
      // configured. This bypasses Vercel's serverless function timeout, which
      // would otherwise kill long-running full-site scans mid-stream. Falls back
      // to the same-origin Next.js proxy routes for local dev.
      const backendBase = process.env.NEXT_PUBLIC_BACKEND_URL;
      const endpoint = scanMode === "site" ? "scan-site" : "scan";
      const email = session?.user?.email;
      const scanSrc = backendBase
        ? `${backendBase.replace(/\/$/, "")}/${endpoint}?url=${encodeURIComponent(scanUrl)}${
            email ? `&email=${encodeURIComponent(email)}` : ""
          }`
        : `/api/${endpoint}?url=${encodeURIComponent(scanUrl)}`;
      const es = new EventSource(scanSrc);
      eventSourceRef.current = es;

      es.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data as string);

          if (data.type === "progress") {
            setProgress({ message: data.message as string, percent: data.percent as number });

            // Parse checked/total out of messages like "Checked 5 of 32 links" or "Scanning page 4/37: /about"
            const match = (data.message as string).match(/(\d+)\s+of\s+(\d+)/) || (data.message as string).match(/(\d+)\/(\d+)/);
            if (match) {
              setCheckedCount(parseInt(match[1], 10));
              setTotalCount(parseInt(match[2], 10));
            }
          } else if (data.type === "result") {
            const linkResults = data.data as LinkResult[];
            setResults(linkResults);
            setDetectedBuilders((data.detected_builders as string[]) ?? []);
            setDiff((data.diff as ScanDiff) ?? null);
            setLinkTypes((data.link_types as Partial<Record<ResourceType, number>>) ?? {});
            setTopHosts((data.top_hosts as HostCount[]) ?? []);
            setSchemes((data.schemes as Record<string, number>) ?? {});
            setRedirects((data.redirects as RedirectSummary) ?? null);
            setSiteId((data.site_id as string) ?? null);
            setScanId((data.scan_id as string) ?? null);
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
    [url, scanMode, session]
  );

  // ─── Filtering ─────────────────────────────────────────────────────────────
  const filteredResults = useMemo(() => {
    let list = results;

    // Diff filter. "fixed" findings no longer exist on the page, so they are
    // not in `results` at all — the Fixed panel reads diff.fixed_findings.
    if (diffFilter === "new" || diffFilter === "recurring") {
      list = list.filter((r) => r.diff_status === diffFilter);
    } else if (diffFilter === "fixed") {
      list = [];
    }

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
  }, [results, filter, zoneFilter, search, diffFilter]);

  const healthScore = useMemo(() => calcScore(results), [results]);

  const handleRescan = useCallback(() => {
    if (scanMeta) startScan(scanMeta.scannedUrl);
  }, [scanMeta, startScan]);

  // ─── Fetch history after scan completes ────────────────────────────────────
  useEffect(() => {
    if (!scanComplete || results.length === 0 || !scanMeta) return;

    const fetchHistory = async () => {
      setHistoryLoading(true);
      try {
        const res = await fetch(
          `/api/history?url=${encodeURIComponent(scanMeta.scannedUrl)}`
        );
        if (res.ok) {
          const data = (await res.json()) as { history?: HistoryScanEntry[] };
          const allHistory = data.history ?? [];

          // The newest entry is normally the scan we just ran, so drop it —
          // but only if it really is ours. If saving this scan failed, the
          // newest row is a genuinely older scan and must not be discarded.
          const isCurrentScan = (entry: HistoryScanEntry) =>
            Math.abs(
              new Date(entry.scanned_at).getTime() - scanMeta.scannedAt.getTime()
            ) < 10 * 60 * 1000;

          setHistory(
            allHistory.length > 0 && isCurrentScan(allHistory[0])
              ? allHistory.slice(1)
              : allHistory
          );
        }
      } catch {
        // Non-critical — silently ignore
      } finally {
        setHistoryLoading(false);
      }
    };

    fetchHistory();
  }, [scanComplete, results.length, scanMeta]);

  const scrollToHistory = useCallback(() => {
    historyPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  // ─── Deep link: /?url=… ────────────────────────────────────────────────────
  // Slack's "View Full Report" button lands here. Prefill and scan straight
  // away, otherwise the button just opens an empty scanner.
  //
  // Read from window.location rather than useSearchParams(): the latter opts the
  // whole page into dynamic rendering unless it sits behind a Suspense boundary.
  const deepLinkHandled = useRef(false);
  useEffect(() => {
    if (deepLinkHandled.current) return;
    // Wait for the session, or the scan is attributed to "anonymous" and its
    // history is stored under a different key than the signed-in user's.
    if (sessionStatus === "loading") return;

    const target = new URLSearchParams(window.location.search).get("url");
    if (!target) return;

    let parsed: URL;
    try {
      parsed = new URL(target);
    } catch {
      return;
    }
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return;

    deepLinkHandled.current = true;
    setUrl(target);
    startScan(target);
  }, [sessionStatus, startScan]);

  return (
    <main className="min-h-screen relative overflow-hidden">
      <NavBar />

      {/* Self-heal entry — right side, opens the dedicated page. */}
      <Link
        href="/self-heal"
        className="hidden sm:inline-flex items-center gap-2"
        style={{
          position: "absolute",
          top: 88,
          right: 24,
          zIndex: 20,
          padding: "8px 16px",
          borderRadius: 999,
          fontSize: 14,
          fontWeight: 600,
          border: "1px solid rgba(168,85,247,0.4)",
          background: "rgba(168,85,247,0.14)",
          color: "#c084fc",
          textDecoration: "none",
          backdropFilter: "blur(6px)",
        }}
      >
        <Wrench size={15} /> Self-heal
      </Link>

      {/* ── HERO SECTION ── */}
      <section className="relative pt-28 pb-8 noise-overlay overflow-hidden">
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
          scanMode={scanMode}
          onScanModeChange={setScanMode}
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

          {/* Tracking banner — only if no history */}
          {scanMeta && (
            <TrackingBanner
              scannedUrl={scanMeta.scannedUrl}
              hasHistory={history.length > 0}
            />
          )}

          {/* Report header: builder badge + bucket counts */}
          <section className="relative z-10">
            <ReportHeader results={results} detectedBuilders={detectedBuilders} diff={diff} siteId={siteId} />
          </section>

          {/* Third-party integrations on the scanned page. z-30 so its panel
              overflows above the later results sections (siblings at z-10). */}
          {scanId && scanMeta && (
            <section className="relative z-30 flex justify-end px-4 sm:px-6 lg:px-8 -mt-2">
              <IntegrationsPanel scanId={scanId} pageUrl={scanMeta.scannedUrl} />
            </section>
          )}

          {/* Health score */}
          <section className="relative z-10">
            <HealthScore results={results} />
          </section>

          {/* What Changed diff card — between health score and summary */}
          {history.length > 0 && (
            <WhatChangedCard
              currentResults={results}
              history={history}
            />
          )}

          {/* Summary banner */}
          <section className="relative z-10">
            <SummaryBanner results={results} />
          </section>

          {/* Stats bar */}
          <section className="relative z-10">
            <StatsBar results={results} diff={diff} />
          </section>

          {/* Informational breakdowns */}
          <section className="relative z-10">
            <ResourcePanels linkTypes={linkTypes} topHosts={topHosts} schemes={schemes} redirects={redirects} />
          </section>

          {/* Triage: broken / dead CTA / unverifiable */}
          <section className="relative z-10">
            <IssueSections results={results} siteId={siteId} />
          </section>

          {/* Filter bar */}
          {/* z-30 so the zone/sort dropdowns overflow ABOVE the results table
              section (which is a sibling at z-10); equal z-index would let the
              later table paint over the open dropdown. */}
          <section className="relative z-30">
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
              diff={diff}
              diffFilter={diffFilter}
              onDiffFilterChange={setDiffFilter}
            />
          </section>

          {/* Results table */}
          <section className="relative z-10">
            <ResultsTable
              results={filteredResults}
              sortOption={sortOption}
              scannedUrl={scanMeta?.scannedUrl ?? url}
              healthScore={healthScore}
              // Only offer the History button when there is a panel to scroll to.
              onScrollToHistory={
                historyLoading || history.length > 0 ? scrollToHistory : undefined
              }
            />
          </section>

          {/* Previous scans of this URL. The ref is what the History button
              scrolls to — without it the button silently does nothing. */}
          {(historyLoading || history.length > 0) && (
            <ScanHistoryPanel
              ref={historyPanelRef}
              history={history}
              loading={historyLoading}
            />
          )}
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
