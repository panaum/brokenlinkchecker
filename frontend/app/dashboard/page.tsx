"use client";

import React, { useState, useEffect, useMemo } from "react";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import {
  Play,
  Loader2,
  Download,
  Plus,
  Trophy,
  AlertCircle,
  Clock,
  X,
  Link2,
} from "lucide-react";
import { DashboardSite, DashboardScan } from "@/types";
import NavBar from "@/components/NavBar";
import Link from "next/link";

// --- Helpers ---
const STATUS_COLORS = {
  green: "#3B6D11",
  amber: "#BA7517",
  red: "#A32D2D",
  gray: "#888780",
};

const PILL_COLORS = {
  red: { bg: "#FCEBEB", text: "#791F1F" },
  amber: { bg: "#FAEEDA", text: "#633806" },
  gray: { bg: "#F3F4F6", text: "#374151" },
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
  const [newSiteFreq, setNewSiteFreq] = useState("Daily");

  const fetchDashboard = async () => {
    try {
      const res = await fetch("/api/dashboard");
      if (!res.ok) throw new Error("Failed to fetch dashboard data");
      const data = (await res.json()) as { sites?: DashboardSite[] };
      setSites(data.sites ?? []);
      
      // Generate some mock activity feed based on real data
      const mockFeed: FeedItem[] = (data.sites ?? [])
        .filter(s => s.scans && s.scans.length > 0)
        .map(s => {
           const latest = s.scans.sort((a,b) => new Date(a.scanned_at).getTime() - new Date(b.scanned_at).getTime()).pop()!;
           const isGood = latest.health_score >= 90;
           return {
             id: s.id + latest.id,
             type: isGood ? "success" as const : "broken" as const,
             siteName: s.name || s.url,
             description: isGood ? "Scan completed successfully" : `Found ${latest.broken_count} broken links`,
             context: isGood ? `${latest.total_links} links checked` : "Review results to fix",
             timestamp: latest.scanned_at
           };
        })
        .sort((a,b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
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
    document.body.style.backgroundColor = "#f9fafb"; // Force light bg for this page
    fetchDashboard();
    
    return () => {
      document.body.style.backgroundColor = ""; // cleanup
    }
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
        const site = sites.find(s => s.id === id);
        setFeed(prev => [{
          id: Date.now().toString(),
          type: "success",
          siteName: site?.name || site?.url || "Site",
          description: "Manual scan completed",
          context: "Initiated from dashboard",
          timestamp: new Date().toISOString()
        }, ...prev].slice(0, 5));
        
        await fetchDashboard();
      }
    } catch(e) {
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
      await fetch('/api/sites', {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: newSiteUrl,
          name: newSiteName,
          client: newSiteName,
          freq: newSiteFreq,
          user_email: newSiteEmail || "default@example.com"
        })
      });
      setShowModal(false);
      setNewSiteUrl("");
      setNewSiteName("");
      setNewSiteEmail("");
      setNewSiteFreq("Daily");
      await fetchDashboard();
    } catch (e) {
      console.error(e);
    }
  };

  // --- Derived ---
  const rankedSites = useMemo(() => {
    return [...sites]
      .filter((s) => s.scans && s.scans.length > 0)
      .map(s => {
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
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
         <Loader2 className="animate-spin text-gray-400" size={32} />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 font-sans" style={{ paddingTop: 56 }}>
      <NavBar />
      <div className="max-w-7xl mx-auto space-y-8 p-8">
        {/* Header & Quick Actions */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-gray-900">Site Health Dashboard</h1>
            <p className="text-gray-500 mt-1">Overview of all monitored properties</p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleScanAll}
              className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-800 text-sm font-medium border border-gray-300 transition-colors flex items-center gap-2"
            >
              <Play size={16} /> Scan All Sites
            </button>
            <button
              onClick={handleExportAll}
              className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-800 text-sm font-medium border border-gray-300 transition-colors flex items-center gap-2"
            >
              <Download size={16} /> Export All Reports
            </button>
            <button
              onClick={() => setShowModal(true)}
              className="px-4 py-2 bg-gray-900 hover:bg-gray-800 text-white text-sm font-medium border border-gray-900 transition-colors flex items-center gap-2"
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
            
            const isOverdue = site.last_scanned_at ? Date.now() - new Date(site.last_scanned_at).getTime() > 7 * 24 * 60 * 60 * 1000 : false;
            const sparkData = sortedScans.slice(-5).map((s, i) => ({ val: s.health_score, i }));

            return (
              <div key={site.id} className="bg-white border border-gray-200 p-5 flex flex-col justify-between">
                <div>
                  {/* Top row: Name + dot */}
                  <div className="flex items-start justify-between gap-4 mb-1 min-w-0">
                    <div className="flex-1 min-w-0">
                       <div className="flex items-center gap-2 mb-1">
                         <h3 className="text-sm font-medium text-gray-900 whitespace-nowrap overflow-hidden text-ellipsis max-w-full">
                           {site.name ? site.name : <span className="text-gray-400 font-normal">No client name</span>}
                         </h3>
                       </div>
                       <p className="text-xs text-gray-500 font-normal truncate">{site.client || "No client specified"}</p>
                       <p className="text-xs text-gray-400 font-mono mt-1 whitespace-nowrap overflow-hidden text-ellipsis max-w-full">{site.url}</p>
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
                        {currentScore !== null && (
                          <span className="text-sm text-gray-400">/ 100</span>
                        )}
                      </div>
                      <div className="mt-2 flex items-center gap-1.5 text-sm font-medium">
                        {currentScore === null ? (
                          <span className="text-gray-400">No data</span>
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
                        <div className="w-full h-full flex items-center justify-center text-[12px] text-gray-400 text-center leading-tight">
                          Scan to build trend
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Issue Pills */}
                  <div className="mt-6 flex flex-wrap gap-2">
                    <button
                      className="px-2.5 py-1 text-xs font-medium border border-transparent transition-opacity hover:opacity-80"
                      style={{ backgroundColor: PILL_COLORS.red.bg, color: PILL_COLORS.red.text }}
                    >
                      {latestScan?.broken_count ?? 0} Broken
                    </button>
                    <button
                      className="px-2.5 py-1 text-xs font-medium border border-transparent transition-opacity hover:opacity-80"
                      style={{ backgroundColor: PILL_COLORS.amber.bg, color: PILL_COLORS.amber.text }}
                    >
                      {latestScan?.dead_cta_count ?? 0} Dead CTAs
                    </button>
                    <button
                      className="px-2.5 py-1 text-xs font-medium border border-transparent transition-opacity hover:opacity-80"
                      style={{ backgroundColor: PILL_COLORS.gray.bg, color: PILL_COLORS.gray.text }}
                    >
                      {latestScan?.total_links ?? 0} Total
                    </button>
                  </div>
                </div>

                {/* Footer details & Action */}
                <div className="mt-8 pt-4 border-t border-gray-100 flex items-center justify-between">
                  <div className="flex flex-col gap-1">
                    <span className="text-xs font-normal" style={{ color: isOverdue ? STATUS_COLORS.red : STATUS_COLORS.gray }}>
                      Last scan: {relTime(site.last_scanned_at)}
                      {isOverdue && " · overdue"}
                    </span>
                    <span className="text-xs font-normal text-gray-400">
                      Next scan: {site.freq === 'Daily' ? 'Tomorrow at 9:00 AM' : site.freq === 'Weekly' ? 'Friday at 10:00 AM' : 'Not scheduled'} · {site.freq || 'Daily'}
                    </span>
                  </div>
                  <div className="flex gap-2">
                     <Link
                        href={`/?url=${encodeURIComponent(site.url)}`}
                        className="flex items-center justify-center px-3 py-1.5 border border-gray-300 bg-white hover:bg-gray-50 text-gray-800 text-xs font-medium transition-colors"
                     >
                        <Link2 size={14} />
                     </Link>
                     <button
                        onClick={() => handleScanSite(site.id, site.url)}
                        disabled={isScanning}
                        className="flex items-center justify-center w-24 py-1.5 border border-gray-300 bg-white hover:bg-gray-50 text-gray-800 text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                     >
                        {isScanning ? <Loader2 size={14} className="animate-spin text-gray-500" /> : "Scan Now"}
                     </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Lower section: League Table & Activity Feed */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 pt-6 pb-12">
          {/* League Table */}
          <div className="lg:col-span-2 bg-white border border-gray-200 p-6">
            <h2 className="text-lg font-bold text-gray-900 mb-6">Health League Table</h2>
            <div className="space-y-4">
              {rankedSites.length === 0 ? (
                <p className="text-sm text-gray-500">No scanned sites yet.</p>
              ) : (
                rankedSites.map((site, index) => {
                  const color = getStatusColor(site.score);
                  return (
                    <div key={site.id} className="flex items-center gap-4">
                      <div className="w-8 flex justify-center">
                        {index === 0 ? (
                          <Trophy size={20} className="text-yellow-500" />
                        ) : (
                          <span className="text-sm font-medium text-gray-400">#{index + 1}</span>
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex justify-between items-baseline mb-1">
                          <p className="text-sm font-medium text-gray-900 truncate">{site.name || site.url}</p>
                          <span className="text-sm font-medium ml-2" style={{ color }}>
                            {site.score}
                          </span>
                        </div>
                        <div className="w-full bg-gray-100 h-1.5">
                          <div className="h-full transition-all duration-500" style={{ width: `${site.score}%`, backgroundColor: color }} />
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Recent Issues Feed */}
          <div className="bg-white border border-gray-200 p-6">
            <h2 className="text-lg font-bold text-gray-900 mb-6">Recent Activity</h2>
            <div className="space-y-6">
              {feed.length === 0 && <p className="text-sm text-gray-500">No recent activity.</p>}
              {feed.map((item) => {
                let iconColor = STATUS_COLORS.gray;
                if (item.type === "broken") iconColor = STATUS_COLORS.red;
                if (item.type === "cta") iconColor = STATUS_COLORS.amber;
                if (item.type === "success") iconColor = STATUS_COLORS.green;

                return (
                  <div key={item.id} className="flex items-start gap-3">
                    <div className="w-2 h-2 rounded-full mt-1.5 shrink-0" style={{ backgroundColor: iconColor }} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-900 font-medium truncate">
                        {item.siteName} <span className="font-normal text-gray-600">— {item.description}</span>
                      </p>
                      <p className="text-xs text-gray-400 font-normal mt-0.5 truncate">{item.context}</p>
                    </div>
                    <span className="text-xs text-gray-400 font-normal whitespace-nowrap shrink-0">{relTime(item.timestamp)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Add Site Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="bg-white border border-gray-200 p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-bold text-gray-900">Add New Site</h3>
              <button onClick={() => setShowModal(false)} className="text-gray-400 hover:text-gray-900">
                <X size={20} />
              </button>
            </div>
            <form onSubmit={handleAddSite} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
                <input
                  type="url"
                  required
                  value={newSiteUrl}
                  onChange={(e) => setNewSiteUrl(e.target.value)}
                  className="w-full border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-gray-900 bg-white text-gray-900"
                  placeholder="https://example.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Client Name</label>
                <input
                  type="text"
                  required
                  value={newSiteName}
                  onChange={(e) => setNewSiteName(e.target.value)}
                  className="w-full border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-gray-900 bg-white text-gray-900"
                  placeholder="Acme Corp"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Notification Email</label>
                <input
                  type="email"
                  required
                  value={newSiteEmail}
                  onChange={(e) => setNewSiteEmail(e.target.value)}
                  className="w-full border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-gray-900 bg-white text-gray-900"
                  placeholder="alerts@acme.corp"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Scan Frequency</label>
                <select
                  value={newSiteFreq}
                  onChange={(e) => setNewSiteFreq(e.target.value)}
                  className="w-full border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-gray-900 bg-white text-gray-900"
                >
                  <option>Daily</option>
                  <option>Weekly</option>
                  <option>Monthly</option>
                  <option>On Demand</option>
                </select>
              </div>
              <div className="pt-4 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-900"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-gray-900 hover:bg-gray-800 text-white text-sm font-medium border border-gray-900 transition-colors"
                >
                  Add Site
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
