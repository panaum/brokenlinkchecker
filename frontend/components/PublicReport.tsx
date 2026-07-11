"use client";

import React, { useMemo, useState } from "react";
import { Printer, ScanEye } from "lucide-react";
import { SharedReport, LinkResult } from "@/types";
import XrayView from "@/components/XrayView";

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
function scoreColor(s: number): string {
  if (s >= 90) return "var(--signal)";
  if (s >= 70) return "var(--status-attention)";
  return "var(--status-broken)";
}
function bucketOf(r: LinkResult): "broken" | "dead_cta" | "unverifiable" {
  if (r.bucket) return r.bucket === "ok" ? "unverifiable" : r.bucket;
  if (r.label === "broken") return "broken";
  if (r.label === "dead_cta") return "dead_cta";
  return "unverifiable";
}
const RANK = { broken: 0, dead_cta: 1, unverifiable: 2 } as const;
const BUCKET_META = {
  broken: { cls: "ds-status-broken", label: "Broken" },
  dead_cta: { cls: "ds-status-attention", label: "Dead CTA" },
  unverifiable: { cls: "ds-status-neutral", label: "Unverifiable" },
} as const;

// The client-facing report. NO internal controls — no re-check, no self-heal,
// no settings. Read-only evidence.
export default function PublicReport({ report }: { report: SharedReport }) {
  const [showXray, setShowXray] = useState(false);
  const domain = domainOf(report.url);
  const R = 46;
  const C = 2 * Math.PI * R;

  const issues = useMemo(
    () =>
      report.results_json
        .filter((r) => r.label !== "ok")
        .sort((a, b) => RANK[bucketOf(a)] - RANK[bucketOf(b)]),
    [report.results_json],
  );

  const verdict =
    report.broken_count > 0
      ? `${report.broken_count} broken ${report.broken_count === 1 ? "link is" : "links are"} turning visitors away.`
      : report.dead_cta_count > 0
        ? `${report.dead_cta_count} call-to-action${report.dead_cta_count === 1 ? "" : "s"} lead nowhere.`
        : "All clear — no broken links found.";

  return (
    <main className="ds-container" style={{ maxWidth: 980, padding: "40px 24px 80px" }}>
      {/* Running header, print only — domain · date · score on every page. */}
      <div className="print-only report-print-header">
        <span>{domain}</span>
        <span>{new Date(report.scanned_at).toLocaleDateString()} · {report.health_score}/100</span>
      </div>

      {/* Minimal header — wordmark + print, no app nav. */}
      <div className="report-toolbar" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 28 }}>
        <span className="font-display" style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.02em" }}>
          Link<span style={{ color: "var(--signal)" }}>Spy</span>
        </span>
        <button className="ds-btn-ghost no-print" onClick={() => window.print()} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <Printer size={15} /> Print / PDF
        </button>
      </div>

      {/* Verdict block */}
      <section className="ds-card ds-card-pad report-verdict" style={{ display: "flex", alignItems: "center", gap: "var(--space-6)", flexWrap: "wrap", marginBottom: "var(--space-5)" }}>
        <div style={{ position: "relative", width: 112, height: 112, flexShrink: 0 }}>
          <svg width="112" height="112" viewBox="0 0 112 112">
            <circle cx="56" cy="56" r={R} fill="none" stroke="rgba(150,210,200,0.08)" strokeWidth="8" />
            <circle cx="56" cy="56" r={R} fill="none" stroke={scoreColor(report.health_score)} strokeWidth="8" strokeLinecap="round"
              strokeDasharray={C} strokeDashoffset={C * (1 - report.health_score / 100)} transform="rotate(-90 56 56)" />
          </svg>
          <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
            <span className="font-mono" style={{ fontSize: 30, fontWeight: 700, color: scoreColor(report.health_score), lineHeight: 1 }}>{report.health_score}</span>
            <span className="font-mono ds-text-muted" style={{ fontSize: 11 }}>/ 100</span>
          </div>
        </div>
        <div style={{ flex: 1, minWidth: 260 }}>
          <div className="font-mono ds-text-muted" style={{ fontSize: 12 }}>{domain}</div>
          <div className="font-display ds-text-primary" style={{ fontSize: "var(--text-display)", fontWeight: 700, lineHeight: 1.15, marginTop: 4 }}>
            {verdict}
          </div>
          <div className="ds-text-secondary font-mono" style={{ fontSize: 12, marginTop: 8 }}>
            {report.total_links} links checked · scanned {new Date(report.scanned_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}
          </div>
        </div>
        {issues.length > 0 && (
          <button className="ds-btn-ghost no-print" onClick={() => setShowXray((v) => !v)} style={{ display: "inline-flex", alignItems: "center", gap: 8, ...(showXray ? { borderColor: "var(--signal)", color: "var(--signal)" } : {}) }}>
            <ScanEye size={15} /> X-ray view
          </button>
        )}
      </section>

      {showXray && (
        <section className="no-print" style={{ marginBottom: "var(--space-5)" }}>
          <XrayView results={report.results_json} pageUrl={report.url} />
        </section>
      )}

      {/* Issues by impact */}
      <section className="ds-card ds-card-pad report-issues">
        <h2 className="font-display ds-text-primary" style={{ fontSize: "var(--text-heading)", fontWeight: 700, marginBottom: 16 }}>
          Issues by impact
        </h2>
        {issues.length === 0 ? (
          <p className="ds-text-secondary" style={{ fontSize: "var(--text-body)" }}>All clear. {report.total_links} links verified.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {issues.map((r, i) => {
              const b = bucketOf(r);
              const meta = BUCKET_META[b];
              return (
                <div key={(r.fingerprint || r.url) + i} className="report-issue" style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "12px 0", borderTop: i ? "1px solid var(--border-subtle)" : "none" }}>
                  <span className={`ds-status ${meta.cls}`} style={{ marginTop: 2, flexShrink: 0 }}>
                    <span className="ds-status-dot" />{meta.label}
                  </span>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="ds-text-primary" style={{ fontSize: "var(--text-body)" }}>{r.anchor_text || "(no anchor text)"}</div>
                    <div className="ds-text-muted font-mono" style={{ fontSize: 12, wordBreak: "break-all" }}>{r.url}</div>
                    {r.reason && <div className="ds-text-secondary" style={{ fontSize: "var(--text-caption)", marginTop: 2 }}>{r.reason}</div>}
                  </div>
                  {r.status_code != null && (
                    <span className="font-mono" style={{ fontSize: 12, color: "var(--status-broken)", flexShrink: 0 }}>{r.status_code}</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <p className="ds-text-muted" style={{ fontSize: "var(--text-caption)", textAlign: "center", marginTop: 28 }}>
        Read-only report generated by LinkSpy.
      </p>
    </main>
  );
}
