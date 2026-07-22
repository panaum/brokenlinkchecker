"use client";

import React, { useState, useEffect, useMemo, useRef } from "react";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import {
  Loader2,
  Download,
  Plus,
  Play,
  X,
  Trash2,
  MoreHorizontal,
  Settings,
  ExternalLink,
  ChevronRight,
} from "lucide-react";
import { DashboardSite, DashboardScan } from "@/types";
import NavBar from "@/components/NavBar";
import { Avatar } from "@/components/Avatar";
import WatchdogPanel from "@/components/WatchdogPanel";
import { cleanStreakDays, fixedThisMonth } from "@/lib/history";
import { middleTruncateUrl } from "@/lib/format";
import Link from "next/link";

// --- Helpers ---
function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url.replace(/^https?:\/\//, "").replace(/^www\./, "").split("/")[0];
  }
}

// A card never shows a "No client name" placeholder. It shows the given name,
// or falls back to the domain — always something real.
function displayName(site: DashboardSite): string {
  return site.name?.trim() || domainOf(site.url);
}


// One status language. A never-scanned site is NEUTRAL gray, never a warning.
function siteStatus(latest: DashboardScan | null): { cls: string; word: string } {
  if (!latest) return { cls: "ds-status-neutral", word: "Not scanned yet" };
  if ((latest.broken_count ?? 0) > 0) return { cls: "ds-status-broken", word: "Broken links" };
  if ((latest.dead_cta_count ?? 0) > 0) return { cls: "ds-status-attention", word: "Needs attention" };
  return { cls: "ds-status-healthy", word: "Healthy" };
}

function relTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "Never scanned";
  const ms = new Date(dateStr).getTime();
  const diffMins = Math.floor((Date.now() - ms) / 60000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  return `${Math.floor(diffHrs / 24)}d ago`;
}

function sortedScansOf(site: DashboardSite): DashboardScan[] {
  return [...(site.scans ?? [])].sort(
    (a, b) => new Date(a.scanned_at).getTime() - new Date(b.scanned_at).getTime(),
  );
}

// --- One card: at-a-glance only. Config lives on the Site Detail page. ---
// Stability band → a health-coded chip (never violet — health has its own
// colors). "sturdy" reads calm, "brittle" asks for attention.
const BAND_CHIP: Record<string, { label: string; cls: string }> = {
  sturdy: { label: "Sturdy", cls: "ds-status-healthy" },
  normal: { label: "Steady", cls: "ds-status-neutral" },
  brittle: { label: "Brittle", cls: "ds-status-attention" },
};

function SiteCard({
  site,
  scanning,
  onRescan,
  onDelete,
  band,
}: {
  site: DashboardSite;
  scanning: boolean;
  onRescan: () => void;
  onDelete: () => void;
  band?: string;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMenuOpen(false); };
    document.addEventListener("mousedown", onDoc);
    window.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); window.removeEventListener("keydown", onKey); };
  }, [menuOpen]);

  const scans = sortedScansOf(site);
  const latest = scans.length ? scans[scans.length - 1] : null;
  const prev = scans.length > 1 ? scans[scans.length - 2] : null;
  const score = latest?.health_score ?? null;
  const diff = prev && latest ? latest.health_score - prev.health_score : null;
  const status = siteStatus(latest);
  const spark = scans.slice(-6).map((s, i) => ({ val: s.health_score, i }));
  const streak = cleanStreakDays(scans);

  // Issue summary as one plain line — no wall of pills.
  let issueLine = "No issues found";
  if (latest) {
    const parts: string[] = [];
    if (latest.broken_count) parts.push(`${latest.broken_count} broken`);
    if (latest.dead_cta_count) parts.push(`${latest.dead_cta_count} dead CTA${latest.dead_cta_count > 1 ? "s" : ""}`);
    if (parts.length) issueLine = parts.join(" · ");
  } else {
    issueLine = "Run the first scan to see issues";
  }

  return (
    <div
      className="group ds-card ds-card-hover ds-rise"
      // While the overflow menu is open, lift the whole card above its grid
      // siblings so the menu isn't painted under the card below it.
      style={{ padding: "var(--space-4) var(--space-5)", display: "flex", flexDirection: "column", gap: "var(--space-3)", minHeight: 168, position: "relative", zIndex: menuOpen ? 40 : undefined }}
    >
      {/* Header: initial + name/domain + status dot */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
        <Avatar name={displayName(site)} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="ds-text-primary" style={{ fontSize: "var(--text-body)", fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {displayName(site)}
          </div>
          <div className="ds-text-muted font-mono" style={{ fontSize: "var(--text-caption)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={site.url}>
            {middleTruncateUrl(site.url)}
          </div>
        </div>
        {band && BAND_CHIP[band] && (
          <span className={`ds-status ${BAND_CHIP[band].cls}`} style={{ flexShrink: 0 }} title="Stability band — how often this site breaks over time">
            {BAND_CHIP[band].label}
          </span>
        )}
        <span className={`ds-status ${status.cls}`} style={{ flexShrink: 0 }}>
          <span className="ds-status-dot" />
        </span>
        <Link
          href={`/dashboard/${site.id}`}
          aria-label={`Open ${displayName(site)}`}
          title="Open site"
          className="nudge-x ds-text-muted"
          style={{ flexShrink: 0, display: "flex", alignItems: "center" }}
        >
          <ChevronRight size={16} />
        </Link>
      </div>

      {/* Score + delta + sparkline */}
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 12 }}>
        <div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
            <span className="font-mono" style={{ fontSize: 34, fontWeight: 700, color: "var(--signal)", lineHeight: 1 }}>
              {score !== null ? score : "—"}
            </span>
            {score !== null && <span className="ds-text-muted font-mono" style={{ fontSize: "var(--text-caption)" }}>/ 100</span>}
          </div>
          <div style={{ fontSize: "var(--text-caption)", marginTop: 4 }}>
            {score === null ? (
              <span className="ds-text-muted">First scan pending</span>
            ) : diff === null ? (
              <span className="ds-text-muted">No previous scan</span>
            ) : diff > 0 ? (
              <span style={{ color: "var(--status-healthy)" }}>▲ +{diff} vs last</span>
            ) : diff < 0 ? (
              <span style={{ color: "var(--status-broken)" }}>▼ {diff} vs last</span>
            ) : (
              <span className="ds-text-muted">No change</span>
            )}
          </div>
        </div>
        <div style={{ width: 88, height: 34 }}>
          {spark.length >= 2 && (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={spark}>
                <Line type="monotone" dataKey="val" stroke="var(--signal)" strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Issue line + status word + clean streak */}
      <div className="ds-text-secondary" style={{ fontSize: "var(--text-caption)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          <span className={`ds-status ${status.cls}`}><span className="ds-status-dot" />{status.word}</span>
          <span className="ds-text-muted"> · {issueLine}</span>
        </span>
        {streak !== null && streak > 0 && (
          <span className="font-mono" style={{ color: "var(--signal)", flexShrink: 0 }} title="Days since the last provable issue">
            {streak}d clean
          </span>
        )}
      </div>

      {/* Footer: last scan + ONE action + overflow */}
      <div style={{ marginTop: "auto", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, paddingTop: "var(--space-3)", borderTop: "1px solid var(--border-subtle)" }}>
        <span className="ds-text-muted" style={{ fontSize: "var(--text-caption)" }}>
          {latest ? `Scanned ${relTime(site.last_scanned_at)}` : "Never scanned"}
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button className="ds-btn-ghost" style={{ padding: "6px 12px", fontSize: "var(--text-caption)" }} onClick={onRescan} disabled={scanning}>
            {scanning ? <Loader2 size={13} className="animate-spin" /> : "Re-scan"}
          </button>
          <div ref={menuRef} style={{ position: "relative" }}>
            <button
              className="ds-btn-ghost"
              style={{ padding: "6px 8px" }}
              aria-haspopup="true"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((o) => !o)}
            >
              <MoreHorizontal size={15} />
            </button>
            {menuOpen && (
              <div
                role="menu"
                style={{
                  position: "absolute", right: 0, top: "calc(100% + 6px)", zIndex: 20, minWidth: 190,
                  background: "var(--surface-raised)", border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-md)", boxShadow: "var(--elev-2)", padding: 6,
                }}
              >
                <Link href={`/dashboard/${site.id}`} className="ds-text-primary" role="menuitem" style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", fontSize: "var(--text-body)", textDecoration: "none", borderRadius: 8 }}>
                  <Settings size={14} /> Site settings
                </Link>
                <Link href={`/?url=${encodeURIComponent(site.url)}`} className="ds-text-primary" role="menuitem" style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", fontSize: "var(--text-body)", textDecoration: "none", borderRadius: 8 }}>
                  <ExternalLink size={14} /> Open in scanner
                </Link>
                <button role="menuitem" onClick={() => { setMenuOpen(false); onDelete(); }} style={{ width: "100%", display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", fontSize: "var(--text-body)", color: "var(--status-broken)", background: "none", border: "none", cursor: "pointer", borderRadius: 8, textAlign: "left" }}>
                  <Trash2 size={14} /> Delete site
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [sites, setSites] = useState<DashboardSite[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanningIds, setScanningIds] = useState<Set<string>>(new Set());
  const [showModal, setShowModal] = useState(false);

  const [newSiteUrl, setNewSiteUrl] = useState("");
  const [newSiteName, setNewSiteName] = useState("");
  const [newSiteEmail, setNewSiteEmail] = useState("");
  const [newSiteFreq, setNewSiteFreq] = useState("Every Hour");

  const [confirmDelete, setConfirmDelete] = useState<{ id: string; name: string } | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  // Stability band per site (from the nightly fragility cache) — a quiet chip,
  // never blocks a card if the endpoint is unavailable.
  const [bands, setBands] = useState<Record<string, string>>({});

  const fetchDashboard = async () => {
    try {
      const res = await fetch("/api/dashboard");
      if (!res.ok) throw new Error("Failed to fetch dashboard data");
      const data = (await res.json()) as { sites?: DashboardSite[] };
      setSites(data.sites ?? []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    document.title = "Dashboard | LinkSpy";
    fetchDashboard();
    fetch("/api/fragility/portfolio")
      .then((r) => (r.ok ? r.json() : { sites: [] }))
      .then((d: { sites?: { site_id: string; band?: string; insufficient?: boolean }[] }) => {
        const map: Record<string, string> = {};
        for (const s of d.sites ?? []) if (s.band && !s.insufficient) map[s.site_id] = s.band;
        setBands(map);
      })
      .catch(() => {});
  }, []);

  const handleScanSite = async (id: string, url: string) => {
    if (scanningIds.has(id)) return;
    setScanningIds((prev) => new Set(prev).add(id));
    try {
      const res = await fetch(`/api/scan?url=${encodeURIComponent(url)}`);
      if (res.ok) await fetchDashboard();
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

  const handleScanAll = () => sites.forEach((s) => handleScanSite(s.id, s.url));

  const handleExportAll = () => alert("Exporting all reports to ZIP...");

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
      setNewSiteUrl(""); setNewSiteName(""); setNewSiteEmail(""); setNewSiteFreq("Every Hour");
      await fetchDashboard();
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteSite = async (id: string) => {
    setDeletingId(id);
    try {
      const res = await fetch(`/api/sites?id=${encodeURIComponent(id)}`, { method: "DELETE" });
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

  // Issues-first, then score ascending (worst first). Never-scanned sinks below
  // scanned ones so attention goes where there's real data.
  const orderedSites = useMemo(() => {
    const scoreOf = (s: DashboardSite): number | null => {
      const scans = sortedScansOf(s);
      return scans.length ? scans[scans.length - 1].health_score : null;
    };
    const issuesOf = (s: DashboardSite): number => {
      const scans = sortedScansOf(s);
      const l = scans[scans.length - 1];
      return l ? (l.broken_count ?? 0) + (l.dead_cta_count ?? 0) : 0;
    };
    return [...sites].sort((a, b) => {
      const ia = issuesOf(a) > 0 ? 0 : 1;
      const ib = issuesOf(b) > 0 ? 0 : 1;
      if (ia !== ib) return ia - ib;
      const sa = scoreOf(a);
      const sb = scoreOf(b);
      if (sa === null) return 1;
      if (sb === null) return -1;
      return sa - sb;
    });
  }, [sites]);

  const fixedCount = useMemo(() => fixedThisMonth(sites.map((s) => s.scans)), [sites]);

  return (
    <div className="relative min-h-screen" style={{ background: "transparent", paddingTop: 56 }}>
      <NavBar />

      <div className="ds-container" style={{ maxWidth: "var(--content-max)", padding: "40px 24px 64px", display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>
        {/* Header — title + ONE primary action; the rest are ghost. */}
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
          <div>
            <h1 className="ds-text-primary font-display" style={{ fontSize: "var(--text-display)", fontWeight: 700, letterSpacing: "-0.5px" }}>
              Sites
            </h1>
            <p className="ds-text-secondary" style={{ fontSize: "var(--text-body)", marginTop: 2 }}>
              {sites.length} monitored {sites.length === 1 ? "property" : "properties"}
              {fixedCount > 0 && (
                <span className="ds-status ds-status-healthy" style={{ marginLeft: 12 }}>
                  <span className="ds-status-dot" /><span className="font-mono">{fixedCount}</span> fixed this month
                </span>
              )}
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button className="ds-btn-ghost" onClick={handleScanAll} disabled={!sites.length} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <Play size={15} /> Scan all
            </button>
            <button className="ds-btn-ghost" onClick={handleExportAll} disabled={!sites.length} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <Download size={15} /> Export
            </button>
            <button className="ds-btn-primary" onClick={() => setShowModal(true)} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <Plus size={16} /> Add site
            </button>
          </div>
        </div>

        {/* Cards grid — 3 across, skeletons while loading. */}
        <div className="stagger" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "var(--space-5)" }}>
          {loading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="ds-card ds-card-pad" style={{ minHeight: 168, display: "flex", flexDirection: "column", gap: 14 }}>
                <div className="ds-skeleton" style={{ height: 34, width: "60%" }} />
                <div className="ds-skeleton" style={{ height: 40, width: "40%" }} />
                <div className="ds-skeleton" style={{ height: 16, width: "80%" }} />
                <div className="ds-skeleton" style={{ height: 30, width: "100%", marginTop: "auto" }} />
              </div>
            ))
          ) : orderedSites.length === 0 ? (
            <div className="ds-card ds-card-pad" style={{ gridColumn: "1 / -1", textAlign: "center", padding: "56px 48px", display: "flex", flexDirection: "column", alignItems: "center", gap: 18 }}>
              <p className="ds-text-secondary" style={{ fontSize: "var(--text-heading)" }}>
                No targets on watch. Add a site to begin surveillance.
              </p>
              <button className="ds-btn-primary" onClick={() => setShowModal(true)} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                <Plus size={16} /> Add site
              </button>
            </div>
          ) : (
            orderedSites.map((site) => (
              <SiteCard
                key={site.id}
                site={site}
                scanning={scanningIds.has(site.id)}
                onRescan={() => handleScanSite(site.id, site.url)}
                onDelete={() => setConfirmDelete({ id: site.id, name: displayName(site) })}
                band={bands[site.id]}
              />
            ))
          )}
        </div>

        {/* Third-party dependency watchdog — one shared outage, all clients. */}
        {!loading && <WatchdogPanel />}
      </div>

      {/* Delete confirmation */}
      {confirmDelete && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16, zIndex: 50 }}>
          <div className="ds-card ds-card-pad" style={{ width: "100%", maxWidth: 400 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
              <div style={{ width: 40, height: 40, borderRadius: 999, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--status-broken-bg)" }}>
                <Trash2 size={18} style={{ color: "var(--status-broken)" }} />
              </div>
              <h3 className="ds-text-primary" style={{ fontSize: "var(--text-heading)", fontWeight: 600 }}>Delete site?</h3>
            </div>
            <p className="ds-text-secondary" style={{ fontSize: "var(--text-body)", marginBottom: 24 }}>
              This permanently removes <span className="ds-text-primary" style={{ fontWeight: 600 }}>{confirmDelete.name}</span> and all its scan history. This can&apos;t be undone.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 12 }}>
              <button className="ds-btn-ghost" onClick={() => setConfirmDelete(null)} disabled={deletingId === confirmDelete.id}>Cancel</button>
              <button
                onClick={() => handleDeleteSite(confirmDelete.id)}
                disabled={deletingId === confirmDelete.id}
                className="ds-btn-primary"
                style={{ background: "var(--status-broken)", display: "inline-flex", alignItems: "center", gap: 8 }}
              >
                {deletingId === confirmDelete.id ? <><Loader2 size={14} className="animate-spin" /> Deleting…</> : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add site */}
      {showModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16, zIndex: 50 }}>
          <div className="ds-card ds-card-pad" style={{ width: "100%", maxWidth: 440 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
              <h3 className="ds-text-primary" style={{ fontSize: "var(--text-heading)", fontWeight: 600 }}>Add new site</h3>
              <button onClick={() => setShowModal(false)} className="ds-text-muted" style={{ background: "none", border: "none", cursor: "pointer" }}><X size={20} /></button>
            </div>
            <form onSubmit={handleAddSite} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {[
                { label: "URL", value: newSiteUrl, set: setNewSiteUrl, type: "url", ph: "https://example.com", req: true },
                { label: "Client name", value: newSiteName, set: setNewSiteName, type: "text", ph: "Acme Corp", req: true },
                { label: "Notification email", value: newSiteEmail, set: setNewSiteEmail, type: "email", ph: "alerts@acme.com", req: true },
              ].map((f) => (
                <div key={f.label}>
                  <label className="ds-text-secondary" style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 6 }}>{f.label}</label>
                  <input
                    type={f.type}
                    required={f.req}
                    value={f.value}
                    onChange={(e) => f.set(e.target.value)}
                    placeholder={f.ph}
                    style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)", borderRadius: "var(--radius-md)", padding: "10px 12px", fontSize: "var(--text-body)", outline: "none" }}
                  />
                </div>
              ))}
              <div>
                <label className="ds-text-secondary" style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 6 }}>Scan frequency</label>
                <select
                  value={newSiteFreq}
                  onChange={(e) => setNewSiteFreq(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)", borderRadius: "var(--radius-md)", padding: "10px 12px", fontSize: "var(--text-body)", outline: "none" }}
                >
                  {["Every Hour", "Every 2 Hours", "Daily", "Weekly", "Monthly", "On Demand"].map((o) => <option key={o}>{o}</option>)}
                </select>
              </div>
              <div style={{ paddingTop: 8, display: "flex", justifyContent: "flex-end", gap: 12 }}>
                <button type="button" className="ds-btn-ghost" onClick={() => setShowModal(false)}>Cancel</button>
                <button type="submit" className="ds-btn-primary">Add site</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
