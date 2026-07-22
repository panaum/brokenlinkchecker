"use client";

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { useSession } from "next-auth/react";
import { AnimatePresence } from "framer-motion";
import { LinkResult, FilterType, SortOption, ScanMeta, ScanDiff, DiffFilter, ResourceType, HostCount, RedirectSummary } from "@/types";
import { ResultsView, type Issue, type ResultsData } from "./issues/page";
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
import ScanVerdict from "@/components/ScanVerdict";
import ShareButton from "@/components/ShareButton";
import XrayView from "@/components/XrayView";
import KeyboardTriage from "@/components/KeyboardTriage";
import { useDynamicFavicon } from "@/lib/useDynamicFavicon";
import { staffToken, withToken } from "@/lib/backendClient";
import { ScanEye } from "lucide-react";
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

// ─── Live scan results -> the new ResultsView's Issue shape ──────────────────
const _REGION_MAP: Record<string, string> = {
  navigation: "nav", nav: "nav", menu: "nav", header: "hero", hero: "hero",
  cta: "hero", banner: "hero", sidebar: "sidebar", aside: "sidebar",
  footer: "footer", body: "body",
};
function _region(cat: string): string {
  const k = (cat || "").toLowerCase();
  for (const key in _REGION_MAP) if (k.includes(key)) return _REGION_MAP[key];
  return "body";
}
function _sev(p?: string | null): "high" | "med" | "low" {
  const x = (p || "").toLowerCase();
  return x === "critical" || x === "high" ? "high" : x === "medium" ? "med" : "low";
}
function _tag(label: string, status?: number | null): { tag: string; cls: "bad" | "warn" | "neutral" } {
  switch (label) {
    case "broken": return { tag: status ? String(status) : "404", cls: "bad" };
    case "dead_cta": return { tag: "Dead", cls: "warn" };
    case "redirect": return { tag: "Redirect", cls: "neutral" };
    case "forbidden": case "blocked": return { tag: "Blocked", cls: "neutral" };
    case "timeout": return { tag: "Timeout", cls: "neutral" };
    case "error": return { tag: "Error", cls: "bad" };
    default: return { tag: label, cls: "neutral" };
  }
}
function _host(u: string): string { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } }
function _path(u: string): string { try { const x = new URL(u); return (x.pathname + x.search) || "/"; } catch { return u; } }
function _summary(label: string): string {
  switch (label) {
    case "broken": return "This link returns an error and no longer resolves.";
    case "dead_cta": return "This button or CTA has no destination set — it goes nowhere when clicked.";
    case "redirect": return "This link redirects before it resolves.";
    default: return "This link could not be verified automatically.";
  }
}
function _clientFix(r: LinkResult): string {
  const a = r.anchor_text || "this link";
  if (r.label === "dead_cta") return `The “${a}” button doesn’t go anywhere when clicked — it needs a destination link.`;
  return `The “${a}” link points to a page that no longer works — update it or remove it.`;
}

function buildResultsData(results: LinkResult[], score: number, scannedUrl: string): ResultsData {
  const flagged = results.filter((r) => r.label !== "ok");
  const issues: Issue[] = flagged.map((r, i) => {
    const { tag, cls } = _tag(r.label, r.status_code);
    const zones = (r.zones && r.zones.length ? r.zones : [r.category]).filter(Boolean) as string[];
    const high = r.priority === "critical" || r.priority === "high";
    const linkType: Issue["linkType"] = r.is_external ? "external" : (r.link_kind === "anchor" ? "anchor" : "internal");
    return {
      id: String(i + 1),
      target: _path(r.url),
      tag, tagCls: cls,
      severity: high ? "HIGH PRIORITY" : "LOWER PRIORITY",
      band: high ? "high" : "low",
      region: _region(r.category || zones[0] || ""),
      pageviews: 0,
      scans: r.days_broken && r.days_broken > 0 ? Math.max(1, Math.round(r.days_broken)) : 1,
      status: "open",
      anchorText: r.anchor_text || "",
      builder: "",
      scoreImpact: "",
      linkType,
      domain: _host(r.url) || _host(scannedUrl),
      summary: r.reason || _summary(r.label),
      clientFix: _clientFix(r),
      occurrences: zones.map((z) => ({ region: z, label: z, severity: _sev(r.priority) })),
      life: [{ date: "now", label: "detected", status: "now" }],
    };
  });
  return {
    siteName: _host(scannedUrl) || scannedUrl,
    totalLinks: results.length,
    healthy: results.filter((r) => r.label === "ok").length,
    broken: results.filter((r) => r.label === "broken" || r.label === "error").length,
    deadCta: results.filter((r) => r.label === "dead_cta").length,
    score,
    issues,
  };
}

export default function HomePage() {
  const { data: session, status: sessionStatus } = useSession();
  const [url, setUrl] = useState("");
  const [scanning, setScanning] = useState(false);
  const [progress, setProgress] = useState({ message: "", percent: 0 });
  const [feed, setFeed] = useState<string[]>([]);
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
  const [showXray, setShowXray] = useState(false);
  const [scanMode, setScanMode] = useState<"single" | "site">("single");
  const eventSourceRef = useRef<EventSource | null>(null);
  const scanningRef = useRef(false);

  // ─── History state ─────────────────────────────────────────────────────────
  const [history, setHistory] = useState<HistoryScanEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const historyPanelRef = useRef<HTMLElement>(null);

  // Tab favicon reflects scan state: radar while scanning, green ring healthy,
  // red dot when the last scan found issues.
  const issueCount = results.filter((r) => r.label !== "ok").length;
  useDynamicFavicon(
    scanning ? "scanning" : scanComplete && results.length > 0 ? (issueCount > 0 ? "issues" : "healthy") : "idle",
  );

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

  // Keyboard triage "x" (or any caller) can open the X-ray view for a finding.
  useEffect(() => {
    const onXray = () => {
      setShowXray(true);
      requestAnimationFrame(() =>
        document.getElementById("xray-section")?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    };
    window.addEventListener("linkspy:xray", onXray as EventListener);
    return () => window.removeEventListener("linkspy:xray", onXray as EventListener);
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
      setShowXray(false);
      setScanComplete(false);
      setScanning(true);
      scanningRef.current = true;
      setProgress({ message: "Initializing scan…", percent: 0 });
      setFeed([]);
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
      void (async () => {
      // Forward the staff token so the backend can verify identity (ignored
      // while PORTAL_ENFORCE is off). SSE can't set headers → ?token=.
      const token = await staffToken();
      const es = new EventSource(withToken(scanSrc, token));
      eventSourceRef.current = es;

      es.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data as string);

          if (data.type === "progress") {
            const msg = data.message as string;
            setProgress({ message: msg, percent: data.percent as number });

            // Accumulate distinct streamed messages into the terminal feed —
            // render the stream instead of collapsing it to a percent.
            setFeed((prev) => (prev[prev.length - 1] === msg ? prev : [...prev, msg].slice(-40)));

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
      })();
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

      {/* Soft indigo aura behind the scanner — gives the frosted input/progress
          panels something to actually frost. Decorative only. */}
      <div className="scanner-aura" aria-hidden />


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
          border: "1px solid var(--border-strong)",
          background: "rgba(79,70,229,0.10)",
          color: "var(--signal)",
          textDecoration: "none",
          backdropFilter: "blur(6px)",
        }}
      >
        <Wrench size={15} /> Self-heal
      </Link>

      {/* ── HERO SECTION ── */}
      <section className="relative pt-28 pb-8 overflow-hidden">
        {/* Hero content */}
        <div className="relative z-10 text-center px-4">
          {/* Badge pill — soft accent tint (matches the Dashboard's active-nav
              treatment), not a solid indigo block. */}
          <div
            className="ds-rise ds-delay-1 inline-flex items-center gap-2 px-4 py-2 rounded-full mb-6"
            style={{
              background: "rgba(79,70,229,0.10)",
              boxShadow: "inset 0 0 0 1px rgba(79,70,229,0.15)",
            }}
          >
            <span className="w-2 h-2 rounded-full animate-pulse-dot" style={{ background: "var(--status-healthy)" }} />
            <span
              className="text-sm"
              style={{
                fontFamily: "var(--font-poppins), Poppins, sans-serif",
                fontWeight: 500,
                color: "var(--signal)",
              }}
            >
              Link Auditor
            </span>
          </div>

          {/* H1 — dark ink, matching the Dashboard's page headings (no colored word). */}
          <h1
            className="ds-rise ds-delay-2 text-4xl sm:text-5xl lg:text-[56px] leading-tight mb-4"
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontWeight: 700,
              letterSpacing: "-0.02em",
              color: "var(--text-primary)",
            }}
          >
            Find Every Broken Link
          </h1>

          {/* Subtitle */}
          <p
            className="ds-rise ds-delay-3 max-w-2xl mx-auto text-lg"
            style={{
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
              fontWeight: 400,
              color: "var(--text-secondary)",
              fontSize: "18px",
            }}
          >
            Paste any URL below — we crawl every nav link, footer, CTA, header
            and body text link and report what&apos;s broken.
          </p>
        </div>
      </section>

      {/* ── URL INPUT ── */}
      <section className="ds-rise ds-delay-4 relative z-10 px-4">
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
              feed={feed}
              onCancel={cancelScan}
            />
          )}
        </AnimatePresence>
      </section>

      {/* ── POST-SCAN RESULTS — new three-column issue UI, live data ── */}
      {scanComplete && results.length > 0 && (
        <section className="relative z-10 px-2 sm:px-4">
          <div
            className="issues-page"
            style={{ background: "transparent", minHeight: "auto", "--font-ui": "inherit", "--font-mono": "ui-monospace, SFMono-Regular, Menlo, monospace" } as React.CSSProperties}
          >
            <div className="issues-wrap" style={{ paddingTop: 8 }}>
              <ResultsView
                key={scanId ?? scanMeta?.scannedUrl ?? url}
                data={buildResultsData(results, healthScore, scanMeta?.scannedUrl ?? url)}
              />
            </div>
          </div>
        </section>
      )}

      {/* ── ZERO LINKS EDGE CASE ── */}
      {scanComplete && results.length === 0 && (
        <section className="relative z-10 px-4 mt-10">
          <div className="w-full max-w-3xl mx-auto glass-card p-10 text-center flex flex-col items-center gap-5">
            <svg width="72" height="72" viewBox="0 0 72 72" fill="none">
              <circle cx="36" cy="36" r="32" stroke="var(--border-subtle)" strokeWidth="2" />
              <path d="M24 36h24M36 24v24" stroke="var(--border-strong)" strokeWidth="2" strokeLinecap="round" />
              <circle cx="36" cy="36" r="8" stroke="var(--border-subtle)" strokeWidth="2" />
            </svg>
            <div>
              <p
                style={{
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                  fontWeight: 600,
                  fontSize: "18px",
                  color: "var(--text-secondary)",
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
                  color: "var(--text-muted)",
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
              className="text-white rounded-xl px-6 py-3 cursor-pointer hover:opacity-90 transition-opacity"
              style={{
                background: "var(--signal)",
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
