"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { DashboardSite, DashboardScan } from "@/types";
import { getPortalToken, clearPortalToken } from "@/lib/backendClient";
import { ShieldCheck, LogOut } from "lucide-react";
import ReportShelf from "@/components/ReportShelf";
import AdsWasteGuard from "@/components/AdsWasteGuard";
import SentinelGuard from "@/components/SentinelGuard";
import LeadTracer from "@/components/LeadTracer";

function domainOf(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}
function latestOf(s: DashboardSite): DashboardScan | null {
  const scans = [...(s.scans ?? [])].sort((a, b) => new Date(a.scanned_at).getTime() - new Date(b.scanned_at).getTime());
  return scans.length ? scans[scans.length - 1] : null;
}
function siteHealth(latest: DashboardScan | null): { cls: string; word: string } {
  if (!latest) return { cls: "ds-status-neutral", word: "Not scanned yet" };
  if ((latest.broken_count ?? 0) > 0) return { cls: "ds-status-broken", word: "Needs attention" };
  if ((latest.dead_cta_count ?? 0) > 0) return { cls: "ds-status-attention", word: "Minor issues" };
  return { cls: "ds-status-healthy", word: "Healthy" };
}

// The client-facing portal home. Read-only, scoped, verdict-first. No operator
// surfaces — no re-scan, self-heal, settings, or other clients.
interface Resource { id: string; title: string; url: string }

export default function PortalHome() {
  const router = useRouter();
  const [sites, setSites] = useState<DashboardSite[] | null>(null);
  const [resources, setResources] = useState<Resource[]>([]);
  const [noAuth, setNoAuth] = useState(false);

  const load = useCallback(async () => {
    const token = getPortalToken();
    if (!token) { setNoAuth(true); return; }
    const auth = { Authorization: `Bearer ${token}` };
    try {
      const res = await fetch("/api/portal/dashboard", { headers: auth, cache: "no-store" });
      if (res.status === 401 || res.status === 403) { setNoAuth(true); return; }
      const body = await res.json();
      setSites(body.sites ?? []);
      fetch("/api/portal/resources", { headers: auth, cache: "no-store" })
        .then((r) => r.json()).then((d) => setResources(d.resources ?? [])).catch(() => {});
    } catch {
      setSites([]);
    }
  }, []);

  useEffect(() => { document.title = "Your report | LinkSpy"; load(); }, [load]);

  const signOut = () => { clearPortalToken(); router.replace("/portal/accept"); };

  const issuesTotal = (sites ?? []).reduce((n, s) => {
    const l = latestOf(s);
    return n + (l ? (l.broken_count ?? 0) + (l.dead_cta_count ?? 0) : 0);
  }, 0);

  return (
    <div style={{ minHeight: "100vh", background: "var(--surface-page)" }}>
      {/* Minimal portal header — no agency nav. */}
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 24px", borderBottom: "1px solid var(--border-subtle)" }}>
        <span className="font-display" style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.02em", color: "var(--text-primary)" }}>
          Link<span style={{ color: "var(--signal)" }}>Spy</span> <span className="ds-text-muted" style={{ fontWeight: 500, fontSize: 13 }}>· by Apexure</span>
        </span>
        {!noAuth && (
          <button onClick={signOut} className="ds-text-muted" style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "none", border: "none", cursor: "pointer", fontSize: "var(--text-caption)" }}>
            <LogOut size={14} /> Sign out
          </button>
        )}
      </header>

      <div className="ds-container" style={{ maxWidth: 900, padding: "40px 24px 64px" }}>
        {noAuth ? (
          <div className="ds-card ds-card-pad" style={{ textAlign: "center", padding: 48 }}>
            <div className="font-display ds-text-primary" style={{ fontSize: "var(--text-heading)", fontWeight: 700, marginBottom: 8 }}>Please use your invite link</div>
            <p className="ds-text-secondary" style={{ fontSize: "var(--text-body)" }}>Open the link your Apexure contact sent you to view your report.</p>
          </div>
        ) : sites === null ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="ds-skeleton" style={{ height: 80 }} />
            <div className="ds-skeleton" style={{ height: 120 }} />
          </div>
        ) : (
          <>
            {/* Verdict-first */}
            <section className="ds-card ds-card-pad" style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: "var(--space-5)" }}>
              <ShieldCheck size={40} style={{ color: issuesTotal === 0 ? "var(--status-healthy)" : "var(--status-attention)", flexShrink: 0 }} />
              <div>
                <div className="font-display ds-text-primary" style={{ fontSize: "var(--text-display)", fontWeight: 700, lineHeight: 1.15 }}>
                  {issuesTotal === 0
                    ? "Everything Apexure watches for you is healthy."
                    : `${issuesTotal} ${issuesTotal === 1 ? "item needs" : "items need"} attention — we're on it.`}
                </div>
                <div className="ds-text-secondary" style={{ fontSize: "var(--text-body)", marginTop: 4 }}>
                  {sites.length} {sites.length === 1 ? "property" : "properties"} monitored
                </div>
              </div>
            </section>

            {/* Read-only site cards */}
            {sites.length === 0 ? (
              <div className="ds-card ds-card-pad ds-text-secondary" style={{ textAlign: "center", padding: 40, fontSize: "var(--text-body)" }}>
                No sites are being monitored for you yet.
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "var(--space-4)" }}>
                {sites.map((s) => {
                  const latest = latestOf(s);
                  const health = siteHealth(latest);
                  const score = latest?.health_score ?? null;
                  return (
                    <div key={s.id} className="ds-card ds-card-pad">
                      <div className="ds-text-primary" style={{ fontSize: "var(--text-body)", fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {s.name?.trim() || domainOf(s.url)}
                      </div>
                      <div className="ds-text-muted font-mono" style={{ fontSize: "var(--text-caption)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{domainOf(s.url)}</div>
                      <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginTop: 12 }}>
                        <span className="font-mono" style={{ fontSize: 32, fontWeight: 700, color: "var(--signal)", lineHeight: 1 }}>{score ?? "—"}</span>
                        {score !== null && <span className="ds-text-muted font-mono" style={{ fontSize: "var(--text-caption)" }}>/ 100</span>}
                      </div>
                      <div className={`ds-status ${health.cls}`} style={{ marginTop: 10 }}><span className="ds-status-dot" />{health.word}</div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Verified lead delivery — the record of green, per monitored site */}
            {sites.map((s) => (
              <section key={s.id} className="ds-card ds-card-pad" style={{ marginTop: "var(--space-5)" }}>
                <LeadTracer variant="dark" siteId={s.id} portal />
              </section>
            ))}

            {/* Disaster sentinel — one guard row per monitored site */}
            {sites.map((s) => (
              <section key={s.id} className="ds-card ds-card-pad" style={{ marginTop: "var(--space-5)" }}>
                <SentinelGuard variant="dark" siteId={s.id} portal />
              </section>
            ))}

            {/* Monthly proof-of-work reports */}
            <section className="ds-card ds-card-pad" style={{ marginTop: "var(--space-5)" }}>
              <ReportShelf variant="dark" portal />
            </section>

            {/* Google Ads waste-guard (read-only for clients) */}
            <section className="ds-card ds-card-pad" style={{ marginTop: "var(--space-5)" }}>
              <AdsWasteGuard variant="dark" portal />
            </section>

            {resources.length > 0 && (
              <section className="ds-card ds-card-pad" style={{ marginTop: "var(--space-5)" }}>
                <h2 className="font-display ds-text-primary" style={{ fontSize: "var(--text-heading)", fontWeight: 700, marginBottom: 12 }}>Resources</h2>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                  {resources.map((r) => (
                    <a key={r.id} href={r.url} target="_blank" rel="noreferrer" className="ds-btn-ghost" style={{ display: "inline-flex", alignItems: "center", gap: 8, textDecoration: "none" }}>
                      {r.title}
                    </a>
                  ))}
                </div>
              </section>
            )}

            <p className="ds-text-muted" style={{ fontSize: "var(--text-caption)", textAlign: "center", marginTop: 32 }}>
              Monitored continuously by Apexure. Read-only view.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
