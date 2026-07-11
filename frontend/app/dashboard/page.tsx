"use client";

import React, { useState, useEffect, useMemo } from "react";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import {
  Play,
  Loader2,
  Download,
  Plus,
  Trophy,
  X,
  Link2,
  Trash2,
} from "lucide-react";
import { DashboardSite } from "@/types";
import NavBar from "@/components/NavBar";
import MonitoringPanel from "@/components/MonitoringPanel";
import WatchdogPanel from "@/components/WatchdogPanel";
import ActiveTestingPanel from "@/components/ActiveTestingPanel";
import Link from "next/link";

// --- Helpers ---
// Brightened status colors for legibility on the dark theme.
const STATUS_COLORS = {
  green: "#4ade80",
  amber: "#fbbf24",
  red: "#f87171",
  gray: "#9ca3af",
};

const PILL_COLORS = {
  red: { bg: "rgba(248,113,113,0.12)", text: "#fca5a5" },
  amber: { bg: "rgba(251,191,36,0.12)", text: "#fcd34d" },
  gray: { bg: "rgba(255,255,255,0.06)", text: "rgba(255,255,255,0.7)" },
};

function getStatusColor(score: number | null): string {
  if (score === null || score === undefined) return STATUS_COLORS.gray;
  if (score >= 90) return STATUS_COLORS.green;
  if (score >= 70) return STATUS_COLORS.amber;
  return STATUS_COLORS.red;
}

function relTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "Never scanned";
  const ms = new Date(dateStr).getTime();
  const diffMs = Date.now() - ms;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  return `${diffDays} days ago`;
}

type FeedItem = {
  id: string;
  type: "broken" | "cta" | "success";
  siteName: string;
  description: string;
  context: string;
  timestamp: string;
};

export default function DashboardPage() {
  const [sites, setSites] = useState<DashboardSite[]>([]);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanningIds, setScanningIds] = useState<Set<string>>(new Set());
  const [showModal, setShowModal] = useState(false);

  // New site form state
  const [newSiteUrl, setNewSiteUrl] = useState("");
  const [newSiteName, setNewSiteName] = useState("");
  const [newSiteEmail, setNewSiteEmail] = useState("");
  const [newSiteFreq, setNewSiteFreq] = useState("Every Hour");

  // Issues modal state
  const [issuesModalSite, setIssuesModalSite] = useState<{ url: string; name: string } | null>(null);
  const [siteIssues, setSiteIssues] = useState<any[]>([]);
  const [loadingIssues, setLoadingIssues] = useState(false);

  // Delete-site state
  const [confirmDelete, setConfirmDelete] = useState<{ id: string; name: string } | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchDashboard = async () => {
    try {
      const res = await fetch("/api/dashboard");
      if (!res.ok) throw new Error("Failed to fetch dashboard data");
      const data = (await res.json()) as { sites?: DashboardSite[] };
      setSites(data.sites ?? []);

      // Generate some mock activity feed based on real data
      const mockFeed: FeedItem[] = (data.sites ?? [])
        .filter((s) => s.scans && s.scans.length > 0)
        .map((s) => {
          const latest = s.scans.sort((a, b) => new Date(a.scanned_at).getTime() - new Date(b.scanned_at).getTime()).pop()!;
          const isGood = latest.health_score >= 90;
          return {
            id: s.id + latest.id,
            type: isGood ? ("success" as const) : ("broken" as const),
            siteName: s.name || s.url,
            description: isGood ? "Scan completed successfully" : `Found ${latest.broken_count} broken links`,
            context: isGood ? `${latest.total_links} links checked` : "Review results to fix",
            timestamp: latest.scanned_at,
          };
        })
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
        .slice(0, 5);

      setFeed(mockFeed);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    document.title = "Dashboard | LinkSpy";
    fetchDashboard();
  }, []);

  // --- Actions ---
  const handleScanSite = async (id: string, url: string) => {
    if (scanningIds.has(id)) return;

    setScanningIds((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });

    try {
      const res = await fetch(`/api/scan?url=${encodeURIComponent(url)}`);
      if (res.ok) {
        // add to feed
        const site = sites.find((s) => s.id === id);
        setFeed((prev) =>
          [
            {
              id: Date.now().toString(),
              type: "success" as const,
              siteName: site?.name || site?.url || "Site",
              description: "Manual scan completed",
              context: "Initiated from dashboard",
              timestamp: new Date().toISOString(),
            },
            ...prev,
          ].slice(0, 5)
        );

        await fetchDashboard();
      }
    } catch (e) {
      console.error(e);
    } finally {
      setScanningIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  const handleScanAll = () => {
    sites.forEach((s) => handleScanSite(s.id, s.url));
  };

  const handleExportAll = () => {
    alert("Exporting all reports to ZIP...");
  };

  const handleAddSite = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await fetch("/api/sites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: newSiteUrl,
          name: newSiteName,
          client: newSiteName,
          freq: newSiteFreq,
          user_email: newSiteEmail || "default@example.com",
        }),
      });
      setShowModal(false);
      setNewSiteUrl("");
      setNewSiteName("");
      setNewSiteEmail("");
      setNewSiteFreq("Every Hour");
      await fetchDashboard();
    } catch (e) {
      console.error(e);
    }
  };

  const handleViewIssues = async (siteUrl: string, siteName: string) => {
    setIssuesModalSite({ url: siteUrl, name: siteName });
    setLoadingIssues(true);
    try {
      const res = await fetch(`/api/issues?url=${encodeURIComponent(siteUrl)}`);
      if (res.ok) {
        const data = await res.json();
        setSiteIssues(data.issues || []);
      } else {
        setSiteIssues([]);
      }
    } catch (err) {
      console.error("Failed to fetch issues", err);
      setSiteIssues([]);
    } finally {
      setLoadingIssues(false);
    }
  };

  const handleDeleteSite = async (id: string) => {
    setDeletingId(id);
    try {
      const res = await fetch(`/api/sites?id=${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setSites((prev) => prev.filter((s) => s.id !== id));
        setConfirmDelete(null);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setDeletingId(null);
    }
  };

  // --- Derived ---
  const rankedSites = useMemo(() => {
    return [...sites]
      .filter((s) => s.scans && s.scans.length > 0)
      .map((s) => {
        const sorted = [...(s.scans ?? [])].sort(
          (a, b) => new Date(a.scanned_at).getTime() - new Date(b.scanned_at).getTime()
        );
        const latest = sorted[sorted.length - 1];
        return { ...s, score: latest?.health_score ?? 0 };
      })
      .sort((a, b) => b.score - a.score);
  }, [sites]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "#0a0612" }}>
        <Loader2 className="animate-spin" size={32} style={{ color: "rgba(255,255,255,0.4)" }} />
      </div>
    );
  }

  return (
    <div className="relative min-h-screen text-white overflow-hidden" style={{ background: "#0a0612", paddingTop: 56 }}>
      <NavBar />

      {/* Decorative gradient orbs (match scanner) */}
      <div
        className="absolute top-[-200px] left-[-200px] w-[600px] h-[600px] rounded-full bg-gradient-1 opacity-20 pointer-events-none"
        style={{ filter: "blur(120px)", zIndex: 0 }}
      />
      <div
        className="absolute top-[100px] right-[-150px] w-[400px] h-[400px] rounded-full bg-gradient-3 opacity-15 pointer-events-none"
        style={{ filter: "blur(120px)", zIndex: 0 }}
      />

      <div className="relative z-10 max-w-7xl mx-auto space-y-8 p-8">
        {/* Header & Quick Actions */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 bg-gradient-2 px-4 py-2 rounded-full mb-4">
              <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse-dot" />
              <span className="text-white/90 text-sm font-medium">Site Health</span>
            </div>
            <h1 className="text-3xl font-bold tracking-tight">
              Site Health <span className="gradient-text">Dashboard</span>
            </h1>
            <p className="text-white/50 mt-1">Overview of all monitored properties</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={handleScanAll}
              className="px-4 py-2 text-sm font-medium rounded-xl border transition-colors flex items-center gap-2"
              style={{ background: "rgba(255,255,255,0.05)", borderColor: "rgba(255,255,255,0.1)", color: "rgba(255,255,255,0.85)" }}
            >
              <Play size={16} /> Scan All Sites
            </button>
            <button
              onClick={handleExportAll}
              className="px-4 py-2 text-sm font-medium rounded-xl border transition-colors flex items-center gap-2"
              style={{ background: "rgba(255,255,255,0.05)", borderColor: "rgba(255,255,255,0.1)", color: "rgba(255,255,255,0.85)" }}
            >
              <Download size={16} /> Export All Reports
            </button>
            <button
              onClick={() => setShowModal(true)}
              className="px-4 py-2 bg-gradient-1 text-white text-sm font-medium rounded-xl transition-opacity hover:opacity-90 flex items-center gap-2"
            >
              <Plus size={16} /> Add New Site
            </button>
          </div>
        </div>

        {/* Site Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {sites.map((site) => {
            const isScanning = scanningIds.has(site.id);
            const sortedScans = [...(site.scans ?? [])].sort(
              (a, b) => new Date(a.scanned_at).getTime() - new Date(b.scanned_at).getTime()
            );
            const latestScan = sortedScans.length > 0 ? sortedScans[sortedScans.length - 1] : null;
            const prevScan = sortedScans.length > 1 ? sortedScans[sortedScans.length - 2] : null;

            const currentScore = latestScan?.health_score ?? null;
            const prevScore = prevScan?.health_score ?? null;
            const diff = prevScore !== null && currentScore !== null ? currentScore - prevScore : 0;
            const color = getStatusColor(currentScore);

            const isOverdue = site.last_scanned_at
              ? Date.now() - new Date(site.last_scanned_at).getTime() > 7 * 24 * 60 * 60 * 1000
              : false;
            const sparkData = sortedScans.slice(-5).map((s, i) => ({ val: s.health_score, i }));

            return (
              <div key={site.id} className="glass-card p-5 flex flex-col justify-between">
                <div>
                  {/* Top row: Name + dot */}
                  <div className="flex items-start justify-between gap-4 mb-1 min-w-0">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-sm font-medium text-white whitespace-nowrap overflow-hidden text-ellipsis max-w-full">
                          {site.name ? site.name : <span className="text-white/40 font-normal">No client name</span>}
                        </h3>
                      </div>
                      <p className="text-xs text-white/50 font-normal truncate">{site.client || "No client specified"}</p>
                      <p className="text-xs text-white/40 font-mono mt-1 whitespace-nowrap overflow-hidden text-ellipsis max-w-full">
                        {site.url}
                      </p>
                    </div>
                    <div className="w-3 h-3 rounded-full mt-1 shrink-0" style={{ backgroundColor: color }} />
                  </div>

                  {/* Main Score Area */}
                  <div className="mt-6 flex items-end justify-between">
                    <div>
                      <div className="flex items-baseline gap-2">
                        <span className="text-5xl font-medium" style={{ color }}>
                          {currentScore !== null ? currentScore : "—"}
                        </span>
                        {currentScore !== null && <span className="text-sm text-white/40">/ 100</span>}
                      </div>
                      <div className="mt-2 flex items-center gap-1.5 text-sm font-medium">
                        {currentScore === null ? (
                          <span className="text-white/40">No data</span>
                        ) : diff > 0 ? (
                          <span style={{ color: STATUS_COLORS.green }}>↑ +{diff}</span>
                        ) : diff < 0 ? (
                          <span style={{ color: STATUS_COLORS.red }}>↓ {diff}</span>
                        ) : (
                          <span style={{ color: STATUS_COLORS.gray }}>→ No change</span>
                        )}
                      </div>
                    </div>

                    {/* Sparkline */}
                    <div className="w-24 h-10">
                      {sparkData.length >= 2 ? (
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={sparkData}>
                            <Line type="monotone" dataKey="val" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-[12px] text-white/40 text-center leading-tight">
                          Scan to build trend
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Issue Pills */}
                  <div className="mt-6 flex flex-wrap gap-2">
                    <button
                      onClick={() => {
                        if ((latestScan?.broken_count ?? 0) > 0) {
                          handleViewIssues(site.url, site.name || site.url);
                        }
                      }}
                      className={`px-2.5 py-1 text-xs font-medium rounded-lg transition-opacity ${
                        (latestScan?.broken_count ?? 0) > 0 ? "hover:opacity-80 cursor-pointer" : "cursor-default"
                      }`}
                      style={{ backgroundColor: PILL_COLORS.red.bg, color: PILL_COLORS.red.text }}
                    >
                      {latestScan?.broken_count ?? 0} Broken
                    </button>
                    <button
                      onClick={() => {
                        if ((latestScan?.dead_cta_count ?? 0) > 0) {
                          handleViewIssues(site.url, site.name || site.url);
                        }
                      }}
                      className={`px-2.5 py-1 text-xs font-medium rounded-lg transition-opacity ${
                        (latestScan?.dead_cta_count ?? 0) > 0 ? "hover:opacity-80 cursor-pointer" : "cursor-default"
                      }`}
                      style={{ backgroundColor: PILL_COLORS.amber.bg, color: PILL_COLORS.amber.text }}
                    >
                      {latestScan?.dead_cta_count ?? 0} Dead CTAs
                    </button>
                    <button
                      className="px-2.5 py-1 text-xs font-medium rounded-lg transition-opacity cursor-default"
                      style={{ backgroundColor: PILL_COLORS.gray.bg, color: PILL_COLORS.gray.text }}
                    >
                      {latestScan?.total_links ?? 0} Total
                    </button>
                  </div>
                </div>

                {/* Footer details & Action */}
                <div className="mt-8 pt-4 flex items-center justify-between" style={{ borderTop: "1px solid rgba(255,255,255,0.08)" }}>
                  <div className="flex flex-col gap-1">
                    <span className="text-xs font-normal" style={{ color: isOverdue ? STATUS_COLORS.red : "rgba(255,255,255,0.4)" }}>
                      Last scan: {relTime(site.last_scanned_at)}
                      {isOverdue && " · overdue"}
                    </span>
                    {/* Scheduling is owned by the Monitoring panel below, which
                        shows the real, live cadence. A second hardcoded "next
                        scan at 9 AM" line here was fiction — there is no wall-
                        clock scheduler; the monitor fires on an interval. */}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setConfirmDelete({ id: site.id, name: site.name || site.url })}
                      title="Delete site"
                      className="flex items-center justify-center px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors hover:!border-red-400/40"
                      style={{ background: "rgba(248,113,113,0.06)", borderColor: "rgba(255,255,255,0.1)", color: "#fca5a5" }}
                    >
                      <Trash2 size={14} />
                    </button>
                    <Link
                      href={`/?url=${encodeURIComponent(site.url)}`}
                      className="flex items-center justify-center px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors"
                      style={{ background: "rgba(255,255,255,0.05)", borderColor: "rgba(255,255,255,0.1)", color: "rgba(255,255,255,0.85)" }}
                    >
                      <Link2 size={14} />
                    </Link>
                    <button
                      onClick={() => handleScanSite(site.id, site.url)}
                      disabled={isScanning}
                      className="flex items-center justify-center w-24 py-1.5 rounded-lg border text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      style={{ background: "rgba(255,255,255,0.05)", borderColor: "rgba(255,255,255,0.1)", color: "rgba(255,255,255,0.85)" }}
                    >
                      {isScanning ? <Loader2 size={14} className="animate-spin text-white/50" /> : "Scan Now"}
                    </button>
                  </div>
                </div>
                <div className="mt-4">
                  <MonitoringPanel siteId={site.id} />
                </div>
                <div className="mt-4">
                  <ActiveTestingPanel siteId={site.id} siteUrl={site.url} />
                </div>
              </div>
            );
          })}
        </div>

        {/* Third-party dependency watchdog — one shared outage, all clients. */}
        <div className="pt-6">
          <WatchdogPanel />
        </div>


        {/* Lower section: League Table & Activity Feed */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 pt-6 pb-12">
          {/* League Table */}
          <div className="lg:col-span-2 glass-card p-6">
            <h2 className="text-lg font-bold text-white mb-6">Health League Table</h2>
            <div className="space-y-4">
              {rankedSites.length === 0 ? (
                <p className="text-sm text-white/50">No scanned sites yet.</p>
              ) : (
                rankedSites.map((site, index) => {
                  const color = getStatusColor(site.score);
                  return (
                    <div key={site.id} className="flex items-center gap-4">
                      <div className="w-8 flex justify-center">
                        {index === 0 ? (
                          <Trophy size={20} className="text-yellow-400" />
                        ) : (
                          <span className="text-sm font-medium text-white/40">#{index + 1}</span>
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex justify-between items-baseline mb-1">
                          <p className="text-sm font-medium text-white truncate">{site.name || site.url}</p>
                          <span className="text-sm font-medium ml-2" style={{ color }}>
                            {site.score}
                          </span>
                        </div>
                        <div className="w-full h-1.5 rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
                          <div className="h-full rounded-full transition-all duration-500" style={{ width: `${site.score}%`, backgroundColor: color }} />
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Recent Issues Feed */}
          <div className="glass-card p-6">
            <h2 className="text-lg font-bold text-white mb-6">Recent Activity</h2>
            <div className="space-y-6">
              {feed.length === 0 && <p className="text-sm text-white/50">No recent activity.</p>}
              {feed.map((item) => {
                let iconColor = STATUS_COLORS.gray;
                if (item.type === "broken") iconColor = STATUS_COLORS.red;
                if (item.type === "cta") iconColor = STATUS_COLORS.amber;
                if (item.type === "success") iconColor = STATUS_COLORS.green;

                return (
                  <div key={item.id} className="flex items-start gap-3">
                    <div className="w-2 h-2 rounded-full mt-1.5 shrink-0" style={{ backgroundColor: iconColor }} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-white font-medium truncate">
                        {item.siteName} <span className="font-normal text-white/60">— {item.description}</span>
                      </p>
                      <p className="text-xs text-white/40 font-normal mt-0.5 truncate">{item.context}</p>
                    </div>
                    <span className="text-xs text-white/40 font-normal whitespace-nowrap shrink-0">{relTime(item.timestamp)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {confirmDelete && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="glass-card p-6 w-full max-w-sm">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full flex items-center justify-center shrink-0" style={{ background: "rgba(248,113,113,0.12)" }}>
                <Trash2 size={18} style={{ color: "#fca5a5" }} />
              </div>
              <h3 className="text-lg font-bold text-white">Delete site?</h3>
            </div>
            <p className="text-sm text-white/60 mb-6">
              This permanently removes <span className="text-white font-medium">{confirmDelete.name}</span> and all its scan history. This can&apos;t be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmDelete(null)}
                disabled={deletingId === confirmDelete.id}
                className="px-4 py-2 text-sm font-medium text-white/60 hover:text-white transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeleteSite(confirmDelete.id)}
                disabled={deletingId === confirmDelete.id}
                className="px-4 py-2 text-sm font-medium rounded-xl text-white transition-opacity hover:opacity-90 flex items-center gap-2 disabled:opacity-60"
                style={{ background: "#b91c1c" }}
              >
                {deletingId === confirmDelete.id ? (
                  <>
                    <Loader2 size={14} className="animate-spin" /> Deleting…
                  </>
                ) : (
                  "Delete"
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Site Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="glass-card p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-bold text-white">Add New Site</h3>
              <button onClick={() => setShowModal(false)} className="text-white/40 hover:text-white transition-colors">
                <X size={20} />
              </button>
            </div>
            <form onSubmit={handleAddSite} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-white/70 mb-1">URL</label>
                <input
                  type="url"
                  required
                  value={newSiteUrl}
                  onChange={(e) => setNewSiteUrl(e.target.value)}
                  className="w-full rounded-lg px-3 py-2 text-sm text-white outline-none transition-colors"
                  style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)" }}
                  placeholder="https://example.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-white/70 mb-1">Client Name</label>
                <input
                  type="text"
                  required
                  value={newSiteName}
                  onChange={(e) => setNewSiteName(e.target.value)}
                  className="w-full rounded-lg px-3 py-2 text-sm text-white outline-none transition-colors"
                  style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)" }}
                  placeholder="Acme Corp"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-white/70 mb-1">Notification Email</label>
                <input
                  type="email"
                  required
                  value={newSiteEmail}
                  onChange={(e) => setNewSiteEmail(e.target.value)}
                  className="w-full rounded-lg px-3 py-2 text-sm text-white outline-none transition-colors"
                  style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)" }}
                  placeholder="alerts@acme.corp"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-white/70 mb-1">Scan Frequency</label>
                <select
                  value={newSiteFreq}
                  onChange={(e) => setNewSiteFreq(e.target.value)}
                  className="w-full rounded-lg px-3 py-2 text-sm text-white outline-none transition-colors"
                  style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)" }}
                >
                  <option className="bg-[#1a1225]">Every Hour</option>
                  <option className="bg-[#1a1225]">Every 2 Hours</option>
                  <option className="bg-[#1a1225]">Daily</option>
                  <option className="bg-[#1a1225]">Weekly</option>
                  <option className="bg-[#1a1225]">Monthly</option>
                  <option className="bg-[#1a1225]">On Demand</option>
                </select>
              </div>

              <div className="pt-4 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-sm font-medium text-white/60 hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-gradient-1 text-white text-sm font-medium rounded-xl transition-opacity hover:opacity-90"
                >
                  Add Site
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Issues Modal */}
      {issuesModalSite && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="glass-card p-6 w-full max-w-3xl max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between mb-6 shrink-0">
              <div>
                <h3 className="text-lg font-bold text-white">Current Issues</h3>
                <p className="text-sm text-white/50">{issuesModalSite.name}</p>
              </div>
              <button onClick={() => setIssuesModalSite(null)} className="text-white/40 hover:text-white transition-colors">
                <X size={20} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto">
              {loadingIssues ? (
                <div className="flex justify-center items-center py-12">
                  <Loader2 className="animate-spin text-white/40" size={32} />
                </div>
              ) : siteIssues.length === 0 ? (
                <div className="text-center py-12 text-white/50 text-sm">No open issues found for this site.</div>
              ) : (
                <div className="space-y-3">
                  {siteIssues.map((issue, i) => (
                    <div
                      key={i}
                      className="flex flex-col sm:flex-row gap-4 p-4 rounded-xl transition-colors"
                      style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1.5">
                          <span
                            className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded"
                            style={
                              issue.label === "dead_cta"
                                ? { background: PILL_COLORS.amber.bg, color: PILL_COLORS.amber.text }
                                : issue.label === "broken"
                                ? { background: PILL_COLORS.red.bg, color: PILL_COLORS.red.text }
                                : { background: PILL_COLORS.gray.bg, color: PILL_COLORS.gray.text }
                            }
                          >
                            {issue.label.replace("_", " ")}
                          </span>
                          <span
                            className="text-xs font-medium px-2 py-0.5 rounded"
                            style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: "rgba(255,255,255,0.6)" }}
                          >
                            {issue.category}
                          </span>
                        </div>
                        <p className="text-sm font-medium text-white break-all mb-1.5">
                          <a href={issue.url} target="_blank" rel="noreferrer" className="hover:underline">
                            {issue.url}
                          </a>
                        </p>
                        {issue.anchor_text && (
                          <p
                            className="text-xs text-white/60 inline-block px-2 py-1 rounded"
                            style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)" }}
                          >
                            &quot;{issue.anchor_text}&quot;
                          </p>
                        )}
                      </div>
                      <div className="text-left sm:text-right shrink-0 flex flex-col justify-between pt-1">
                        <span className="text-[11px] text-white/40">
                          First seen: {new Date(issue.first_seen_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
