"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { DashboardSite, DashboardScan } from "@/types";
import NavBar from "@/components/NavBar";
import MonitoringPanel from "@/components/MonitoringPanel";
import DeliveryPanel from "@/components/DeliveryPanel";
import ActiveTestingPanel from "@/components/ActiveTestingPanel";
import BadgeEmbed from "@/components/BadgeEmbed";
import TimeMachine from "@/components/TimeMachine";
import ReportShelf from "@/components/ReportShelf";
import AdsWasteGuard from "@/components/AdsWasteGuard";
import SentinelGuard from "@/components/SentinelGuard";
import InboundTriage from "@/components/InboundTriage";
import ConsentSessions from "@/components/ConsentSessions";
import GovernancePanel from "@/components/GovernancePanel";
import ContractsPanel from "@/components/ContractsPanel";
import LeadTracer from "@/components/LeadTracer";
import IntentMap from "@/components/IntentMap";
import PerformanceLedger from "@/components/PerformanceLedger";
import FragilityPanel from "@/components/FragilityPanel";
import QaBridgePanel from "@/components/QaBridgePanel";
import { cleanStreakDays } from "@/lib/history";

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function scoreColor(score: number | null): string {
  if (score === null) return "var(--status-neutral)";
  if (score >= 90) return "var(--status-healthy)";
  if (score >= 70) return "var(--status-attention)";
  return "var(--status-broken)";
}

interface Issue {
  url: string;
  label: string;
  category: string;
  anchor_text?: string;
  first_seen_at: string;
}

export default function SiteDetailPage() {
  const params = useParams();
  const siteId = String(params.siteId);
  const [site, setSite] = useState<DashboardSite | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"overview" | "promises" | "performance" | "governance" | "contracts" | "settings">("overview");
  const [issues, setIssues] = useState<Issue[] | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/dashboard");
      const data = (await res.json()) as { sites?: DashboardSite[] };
      const found = (data.sites ?? []).find((s) => s.id === siteId) ?? null;
      setSite(found);
    } catch {
      setSite(null);
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    load();
  }, [load]);

  // Load open issues lazily when the site is known.
  useEffect(() => {
    if (!site) return;
    fetch(`/api/issues?url=${encodeURIComponent(site.url)}`)
      .then((r) => (r.ok ? r.json() : { issues: [] }))
      .then((d) => setIssues(d.issues ?? []))
      .catch(() => setIssues([]));
  }, [site]);

  const scans: DashboardScan[] = site
    ? [...(site.scans ?? [])].sort((a, b) => new Date(b.scanned_at).getTime() - new Date(a.scanned_at).getTime())
    : [];
  const latest = scans[0] ?? null;
  const score = latest?.health_score ?? null;
  const streak = cleanStreakDays(scans);
  const name = site?.name?.trim() || (site ? domainOf(site.url) : "");

  return (
    <div className="min-h-screen" style={{ background: "transparent", paddingTop: 56 }}>
      <NavBar />
      <div className="ds-container" style={{ maxWidth: 900, padding: "40px 24px 64px" }}>
        <Link href="/dashboard" className="ds-text-muted" style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 20, fontSize: "var(--text-body)", textDecoration: "none" }}>
          <ArrowLeft size={15} /> All sites
        </Link>

        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="ds-skeleton" style={{ height: 36, width: "40%" }} />
            <div className="ds-skeleton" style={{ height: 120, width: "100%" }} />
          </div>
        ) : !site ? (
          <p className="ds-text-secondary" style={{ fontSize: "var(--text-body)" }}>Site not found.</p>
        ) : (
          <>
            {/* Header */}
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
              <div>
                <h1 className="ds-text-primary" style={{ fontSize: "var(--text-display)", fontWeight: 700, letterSpacing: "-0.5px" }}>{name}</h1>
                <a href={site.url} target="_blank" rel="noopener noreferrer" className="ds-text-secondary" style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: "var(--text-body)", textDecoration: "none", marginTop: 4 }}>
                  {domainOf(site.url)} <ExternalLink size={13} />
                </a>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
                {streak !== null && streak > 0 && (
                  <div style={{ textAlign: "right" }}>
                    <div className="font-mono" style={{ fontSize: "var(--text-display)", fontWeight: 700, color: "var(--signal)", lineHeight: 1 }}>{streak}</div>
                    <div className="ds-text-muted" style={{ fontSize: "var(--text-caption)" }}>{streak === 1 ? "day clean" : "days clean"}</div>
                  </div>
                )}
                {score !== null && (
                  <div style={{ textAlign: "right" }}>
                    <div className="font-mono" style={{ fontSize: "var(--text-display)", fontWeight: 700, color: "var(--signal)", lineHeight: 1 }}>{score}</div>
                    <div className="ds-text-muted" style={{ fontSize: "var(--text-caption)" }}>health score</div>
                  </div>
                )}
              </div>
            </div>

            {/* Tabs */}
            <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border-subtle)", marginBottom: 24 }}>
              {(["overview", "promises", "performance", "governance", "contracts", "settings"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  style={{
                    background: "none", border: "none", cursor: "pointer", padding: "10px 14px",
                    fontSize: "var(--text-body)", fontWeight: 500, textTransform: "capitalize",
                    color: tab === t ? "var(--text-primary)" : "var(--text-muted)",
                    borderBottom: `2px solid ${tab === t ? "var(--accent-solid)" : "transparent"}`,
                    marginBottom: -1,
                  }}
                >
                  {t}
                </button>
              ))}
            </div>

            {tab === "overview" ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
                {/* Delivery — the federation's first cross-app surface: the QA
                    app's pages for this site (renders its own card). */}
                <DeliveryPanel variant="dark" siteId={site.id} />

                {/* Verified lead delivery — the record of green (primary surface) */}
                <div className="ds-card ds-card-pad">
                  <LeadTracer variant="dark" siteId={site.id} canManage />
                </div>

                {/* Disaster sentinel — SSL / domain / indexability / uptime guard cards */}
                <div className="ds-card ds-card-pad">
                  <SentinelGuard variant="dark" siteId={site.id} canManage />
                </div>

                {/* Inbound-404 triage — rank dead URLs by measured visitor demand */}
                <div className="ds-card ds-card-pad">
                  <InboundTriage variant="dark" siteId={site.id} canManage />
                </div>

                {/* Consent behavior observation ledger (PR1 — surfaces land in PR2) */}
                <div className="ds-card ds-card-pad">
                  <ConsentSessions variant="dark" siteId={site.id} canManage />
                </div>

                {/* Fragility & decay — longitudinal read of findings history */}
                <div className="ds-card ds-card-pad">
                  <FragilityPanel variant="dark" siteId={site.id} />
                </div>

                {/* Time machine — scrub through every snapshot of this site. */}
                <div>
                  <h2 className="ds-text-primary font-display" style={{ fontSize: "var(--text-heading)", fontWeight: 700, marginBottom: 12 }}>Time machine</h2>
                  <TimeMachine siteUrl={site.url} />
                </div>

                {/* Vigilance reports — monthly proof-of-work archive + generate */}
                <div className="ds-card ds-card-pad">
                  <ReportShelf variant="dark" siteId={site.id} canGenerate />
                </div>

                {/* Google Ads waste-guard — imported destinations, verified daily */}
                <div className="ds-card ds-card-pad">
                  <AdsWasteGuard variant="dark" siteId={site.id} canManage />
                </div>

                {/* Open issues */}
                <div className="ds-card ds-card-pad">
                  <h2 className="ds-text-primary" style={{ fontSize: "var(--text-heading)", fontWeight: 600, marginBottom: 16 }}>Open issues</h2>
                  {issues === null ? (
                    <div className="ds-skeleton" style={{ height: 60 }} />
                  ) : issues.length === 0 ? (
                    <p className="ds-text-secondary" style={{ fontSize: "var(--text-body)" }}>No open issues on the latest scan.</p>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      {issues.map((issue, i) => {
                        const cls = issue.label === "broken" ? "ds-status-broken" : issue.label === "dead_cta" ? "ds-status-attention" : "ds-status-neutral";
                        return (
                          <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 0", borderTop: i ? "1px solid var(--border-subtle)" : "none" }}>
                            <span className={`ds-status ${cls}`} style={{ marginTop: 3 }}><span className="ds-status-dot" /></span>
                            <div style={{ minWidth: 0, flex: 1 }}>
                              <a href={issue.url} target="_blank" rel="noreferrer" className="ds-text-primary" style={{ fontSize: "var(--text-body)", wordBreak: "break-all", textDecoration: "none" }}>{issue.url}</a>
                              {issue.anchor_text && <div className="ds-text-muted" style={{ fontSize: "var(--text-caption)", marginTop: 2 }}>&ldquo;{issue.anchor_text}&rdquo; · {issue.category}</div>}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Scan history */}
                <div className="ds-card ds-card-pad">
                  <h2 className="ds-text-primary" style={{ fontSize: "var(--text-heading)", fontWeight: 600, marginBottom: 16 }}>Scan history</h2>
                  {scans.length === 0 ? (
                    <p className="ds-text-secondary" style={{ fontSize: "var(--text-body)" }}>No scans yet.</p>
                  ) : (
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "var(--text-body)" }}>
                        <thead>
                          <tr className="ds-text-muted" style={{ textAlign: "left", fontSize: "var(--text-caption)" }}>
                            <th style={{ padding: "8px 8px 8px 0", fontWeight: 500 }}>When</th>
                            <th style={{ padding: 8, fontWeight: 500 }}>Score</th>
                            <th style={{ padding: 8, fontWeight: 500 }}>Broken</th>
                            <th style={{ padding: 8, fontWeight: 500 }}>Dead CTAs</th>
                            <th style={{ padding: 8, fontWeight: 500 }}>Links</th>
                          </tr>
                        </thead>
                        <tbody>
                          {scans.map((s) => (
                            <tr key={s.id} style={{ borderTop: "1px solid var(--border-subtle)", height: 44 }}>
                              <td className="ds-text-secondary" style={{ padding: "0 8px 0 0" }}>{new Date(s.scanned_at).toLocaleString()}</td>
                              <td style={{ padding: 8, color: scoreColor(s.health_score), fontWeight: 600 }}>{s.health_score}</td>
                              <td className="ds-text-secondary" style={{ padding: 8 }}>{s.broken_count}</td>
                              <td className="ds-text-secondary" style={{ padding: 8 }}>{s.dead_cta_count}</td>
                              <td className="ds-text-secondary" style={{ padding: 8 }}>{s.total_links}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            ) : tab === "promises" ? (
              <div className="ds-card ds-card-pad">
                <IntentMap variant="dark" siteId={site.id} canEnroll />
              </div>
            ) : tab === "performance" ? (
              <div className="ds-card ds-card-pad">
                <PerformanceLedger variant="dark" siteId={site.id} canManage />
              </div>
            ) : tab === "governance" ? (
              <div className="ds-card ds-card-pad">
                <GovernancePanel variant="dark" siteId={site.id} />
              </div>
            ) : tab === "contracts" ? (
              // Lead delivery contracts — define & verify what an intact lead is.
              <div className="ds-card ds-card-pad">
                <ContractsPanel siteId={site.id} />
              </div>
            ) : (
              // Settings — all per-site config lives here, off the overview cards.
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
                <div>
                  <h2 className="ds-text-primary" style={{ fontSize: "var(--text-heading)", fontWeight: 600, marginBottom: 4 }}>Monitoring</h2>
                  <p className="ds-text-secondary" style={{ fontSize: "var(--text-caption)", marginBottom: 12 }}>Automatic re-scans on a schedule, with alerts when health drops.</p>
                  <MonitoringPanel siteId={site.id} />
                </div>
                <div>
                  <h2 className="ds-text-primary" style={{ fontSize: "var(--text-heading)", fontWeight: 600, marginBottom: 4 }}>Active form testing</h2>
                  <p className="ds-text-secondary" style={{ fontSize: "var(--text-caption)", marginBottom: 12 }}>Opt in per form to submit a real test entry and confirm delivery. Off by default.</p>
                  <ActiveTestingPanel siteId={site.id} siteUrl={site.url} />
                </div>
                <div>
                  <h2 className="ds-text-primary" style={{ fontSize: "var(--text-heading)", fontWeight: 600, marginBottom: 4 }}>Status badge</h2>
                  <p className="ds-text-secondary" style={{ fontSize: "var(--text-caption)", marginBottom: 12 }}>An embeddable SVG showing this site&apos;s latest health score.</p>
                  <BadgeEmbed siteId={site.id} siteUrl={site.url} />
                </div>
                <div>
                  <h2 className="ds-text-primary" style={{ fontSize: "var(--text-heading)", fontWeight: 600, marginBottom: 4 }}>QA Dashboard link</h2>
                  <p className="ds-text-secondary" style={{ fontSize: "var(--text-caption)", marginBottom: 12 }}>Connect this site to a QA deliverable so the QA app shows each delivery check&apos;s live status (&ldquo;still true today&rdquo;). Internal only.</p>
                  <QaBridgePanel siteId={site.id} />
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
