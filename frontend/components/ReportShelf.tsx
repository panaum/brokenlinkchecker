"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { FileText, Plus, Loader2, ShieldCheck, ArrowRight } from "lucide-react";
import { staffToken, getPortalToken } from "@/lib/backendClient";

interface ReportRow {
  id: string; period_label: string; period_start: string; created_at: string;
  site_name?: string;
  data_json?: { score?: number | null; verdict?: string; all_clear?: boolean; caught_count?: number };
}

type Variant = "dark" | "light";

// Palettes for the two registers. Agency = mission-control dark; client = boardroom light.
const T = {
  dark: {
    ink: "var(--text-primary)", sub: "var(--text-secondary)", muted: "var(--text-muted)",
    card: "var(--surface-card)", raised: "var(--surface-raised)", line: "var(--border-subtle, rgba(255,255,255,0.08))",
    brand: "#a855f7", green: "#4ade80", spine: "rgba(168,85,247,0.5)",
  },
  light: {
    ink: "#1c1a2e", sub: "#55506b", muted: "#928da6",
    card: "#ffffff", raised: "#f4f3f9", line: "#e7e4f0",
    brand: "#7c3aed", green: "#16a34a", spine: "rgba(124,58,237,0.5)",
  },
};

function scoreColor(s: number | null | undefined, green: string): string {
  if (s == null) return "#928da6";
  if (s >= 90) return green;
  if (s >= 70) return "#d97706";
  return "#dc2626";
}

export default function ReportShelf({
  variant, siteId, portal, canGenerate,
}: { variant: Variant; siteId?: string; portal?: boolean; canGenerate?: boolean }) {
  const c = T[variant];
  const [reports, setReports] = useState<ReportRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const token = portal ? getPortalToken() : await staffToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [portal]);

  const load = useCallback(async () => {
    try {
      const url = portal ? "/api/portal/reports" : `/api/sites/${siteId}/reports`;
      const res = await fetch(url, { headers: await authHeaders() });
      const j = await res.json().catch(() => ({ reports: [] }));
      setReports(j.reports || []);
    } catch {
      setReports([]);
    }
  }, [portal, siteId, authHeaders]);

  useEffect(() => { load(); }, [load]);

  const generate = async () => {
    if (!siteId) return;
    setBusy(true); setErr(null);
    try {
      const res = await fetch(`/api/sites/${siteId}/report/generate`, { method: "POST", headers: await authHeaders() });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(j.error || `Could not generate (HTTP ${res.status}).`);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to generate.");
    } finally {
      setBusy(false);
    }
  };

  const heading = (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <FileText size={18} style={{ color: c.brand }} />
        <span style={{ fontFamily: "var(--font-stack-display)", fontWeight: 700, fontSize: 18, color: c.ink }}>Vigilance reports</span>
      </div>
      {canGenerate && siteId && (
        <button onClick={generate} disabled={busy}
          style={{
            display: "inline-flex", alignItems: "center", gap: 7, background: c.brand, color: "#fff", border: "none",
            borderRadius: 9, padding: "8px 14px", fontSize: 13, fontWeight: 600, cursor: busy ? "wait" : "pointer", opacity: busy ? 0.7 : 1,
          }}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          {busy ? "Generating…" : "Generate now"}
        </button>
      )}
    </div>
  );

  // ── Loading ──
  if (reports === null) {
    return (
      <div>
        {heading}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 14 }}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{ height: 150, borderRadius: 14, background: c.raised, border: `1px solid ${c.line}`, opacity: 0.6 }} className="animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div>
      {heading}
      {err && <div style={{ color: "#dc2626", fontSize: 13, marginBottom: 12 }}>{err}</div>}

      {reports.length === 0 ? (
        // ── Designed empty state (not a blank box) ──
        <div style={{
          border: `1px dashed ${c.line}`, borderRadius: 16, padding: "40px 24px", textAlign: "center", background: c.raised,
        }}>
          <ShieldCheck size={30} style={{ color: c.green, marginBottom: 12 }} />
          <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 17, fontWeight: 600, color: c.ink }}>
            No reports on the shelf yet
          </div>
          <div style={{ color: c.sub, fontSize: 14, marginTop: 6, maxWidth: 380, marginInline: "auto" }}>
            {canGenerate
              ? "Generate the first monthly proof-of-work report — the record of everything we watched and caught."
              : "Your monthly proof-of-work reports will appear here as they're published."}
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))", gap: 14 }}>
          {reports.map((r) => {
            const d = r.data_json || {};
            const sc = scoreColor(d.score, c.green);
            return (
              <Link key={r.id} href={`/reports/${r.id}`} className="report-cover"
                style={{
                  display: "block", textDecoration: "none", position: "relative", overflow: "hidden",
                  borderRadius: 14, background: c.card, border: `1px solid ${c.line}`, padding: "18px 18px 16px",
                  transition: "transform 160ms ease, box-shadow 160ms ease",
                }}>
                {/* document spine */}
                <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 4, background: c.spine }} />
                {r.site_name && <div style={{ color: c.muted, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>{r.site_name}</div>}
                <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 20, fontWeight: 800, color: c.ink, letterSpacing: "-0.01em" }}>{r.period_label}</div>
                <div style={{ color: c.sub, fontSize: 12.5, marginTop: 8, lineHeight: 1.4, minHeight: 34,
                  display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                  {d.verdict || "Proof-of-work report"}
                </div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 14 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    {d.score != null && (
                      <span style={{ fontFamily: "var(--font-stack-mono)", fontSize: 15, fontWeight: 700, color: sc }}>{d.score}</span>
                    )}
                    {d.all_clear
                      ? <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: c.green, fontSize: 12 }}><ShieldCheck size={13} /> All clear</span>
                      : (d.caught_count ? <span style={{ color: c.sub, fontSize: 12 }}>{d.caught_count} caught</span> : null)}
                  </div>
                  <ArrowRight size={15} style={{ color: c.muted }} />
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
