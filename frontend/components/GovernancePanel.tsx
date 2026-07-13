"use client";

import { useCallback, useEffect, useState } from "react";
import { ScrollText, ShieldCheck, AlertTriangle, Info, Wrench, Clock } from "lucide-react";
import { staffToken, getPortalToken } from "@/lib/backendClient";

type Variant = "dark" | "light";

interface Check {
  code: string; regime: string; severity: string; statement: string; citation: string;
  evidence: { host?: string; ms_after_load?: number }; first_observed: string | null;
  status: "incident" | "finding"; drift_from: string | null; page_url: string;
  remediation: { text: string; kind: string } | null;
}
interface Regime { header: string; all_clear: boolean; open_checks: Check[]; limitations: Array<{ statement: string }>; pages: number; }
interface Gov { scope_statement: string; regimes: Record<string, Regime>; }

const T = {
  dark: { ink: "var(--text-primary)", sub: "var(--text-secondary)", muted: "var(--text-muted)", card: "var(--surface-card)", raised: "var(--surface-raised)", line: "rgba(255,255,255,0.08)", brand: "#a855f7", good: "#4ade80", bad: "#f87171", high: "#fb923c", info: "#8b93a7", badbg: "rgba(248,113,113,0.12)" },
  light: { ink: "#1c1a2e", sub: "#55506b", muted: "#928da6", card: "#ffffff", raised: "#f4f3f9", line: "#e7e4f0", brand: "#7c3aed", good: "#16a34a", bad: "#dc2626", high: "#ea580c", info: "#8a86a0", badbg: "#fef2f2" },
};
const sevColor = (s: string, c: typeof T.dark) => s === "critical" ? c.bad : s === "high" ? c.high : c.info;
const REGIME_LABEL: Record<string, string> = { UK: "United Kingdom · UK GDPR / PECR", US: "United States · CCPA / CPRA" };
const dstr = (iso: string | null) => iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—";
const soften = (h: string) => h.replace("observations open", "items we're tracking").replace("observation open", "item we're tracking");

export default function GovernancePanel({ variant, siteId, portal }: { variant: Variant; siteId: string; portal?: boolean }) {
  const c = T[variant];
  const [g, setG] = useState<Gov | null>(null);

  const load = useCallback(async () => {
    try { const t = portal ? getPortalToken() : await staffToken(); const r = await fetch(`/api/sites/${siteId}/governance`, { headers: t ? { Authorization: `Bearer ${t}` } : {} }); setG(await r.json()); } catch { setG(null); }
  }, [siteId, portal]);
  useEffect(() => { load(); }, [load]);

  const heading = (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
      <ScrollText size={18} style={{ color: c.brand }} />
      <span style={{ fontFamily: "var(--font-stack-display)", fontWeight: 700, fontSize: 18, color: c.ink }}>Data-governance observations</span>
    </div>
  );
  if (g === null) return <div>{heading}<div className="animate-pulse" style={{ height: 160, borderRadius: 14, background: c.raised, border: `1px solid ${c.line}` }} /></div>;

  const regimes = Object.entries(g.regimes || {});
  return (
    <div>{heading}
      {/* Wording law — scope statement always visible on every client-visible surface */}
      <div style={{ color: c.muted, fontSize: 12, marginBottom: 16, fontStyle: "italic" }}>{g.scope_statement}</div>

      {regimes.length === 0 ? (
        <div style={{ border: `1px dashed ${c.line}`, borderRadius: 14, padding: "32px 20px", textAlign: "center", background: c.raised, color: c.sub, fontSize: 13.5 }}>
          No pages are enrolled for consent observation yet.
        </div>
      ) : regimes.map(([regime, r]) => (
        <div key={regime} style={{ marginBottom: 22 }}>
          <div style={{ fontSize: 11, color: c.muted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>{REGIME_LABEL[regime] || regime}</div>

          {/* ── Verdict-first header ── */}
          {r.all_clear ? (
            <div style={{ borderRadius: 16, padding: "24px 24px", border: `1px solid ${c.line}`, background: c.raised, display: "flex", alignItems: "center", gap: 16 }}>
              <ShieldCheck size={30} style={{ color: c.good, flexShrink: 0 }} />
              <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 20, fontWeight: 800, color: c.ink }}>{portal ? soften(r.header) : r.header}</div>
            </div>
          ) : (
            <>
              <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 20, fontWeight: 800, lineHeight: 1.3, color: c.ink, textWrap: "balance" as "balance", marginBottom: 12 }}>{portal ? soften(r.header) : r.header}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {r.open_checks.map((chk, i) => (
                  <div key={i} style={{ border: `1px solid ${sevColor(chk.severity, c)}`, borderRadius: 12, background: c.badbg, padding: "14px 16px" }}>
                    <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                      <AlertTriangle size={16} style={{ color: sevColor(chk.severity, c), flexShrink: 0, marginTop: 2 }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                          <span style={{ fontSize: 10.5, fontWeight: 700, color: chk.status === "incident" ? c.bad : c.high, textTransform: "uppercase", letterSpacing: "0.05em", border: `1px solid ${c.line}`, padding: "1px 7px", borderRadius: 999 }}>
                            {chk.status === "incident" ? "New — drift" : "Ongoing"}
                          </span>
                          <span style={{ fontSize: 11.5, color: c.muted }}>first observed {dstr(chk.first_observed)}</span>
                        </div>
                        <div style={{ color: c.ink, fontSize: 13.5, fontWeight: 600, marginTop: 6 }}>{chk.statement}</div>
                        <div style={{ color: c.sub, fontSize: 12.5, marginTop: 3 }}>{chk.citation}</div>
                        {/* Incident drift diff — clean on X → observed Y */}
                        {chk.status === "incident" && chk.drift_from && (
                          <div style={{ color: c.bad, fontSize: 12.5, marginTop: 6, fontFamily: "var(--font-stack-mono)" }}>
                            Clean on {dstr(chk.drift_from)} → observed on {dstr(chk.first_observed)} — a change occurred in this window.
                          </div>
                        )}
                        {/* Remediation — technical suggestion, not legal advice */}
                        {!portal && chk.remediation && (
                          <div style={{ display: "flex", alignItems: "flex-start", gap: 7, marginTop: 8, padding: "8px 10px", background: c.raised, borderRadius: 8 }}>
                            <Wrench size={13} style={{ color: c.brand, flexShrink: 0, marginTop: 2 }} />
                            <div style={{ fontSize: 12.5, color: c.sub }}><b style={{ color: c.ink }}>Technical suggestion:</b> {chk.remediation.text}</div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* Declared limitations (neutral, never a verdict) */}
          {r.limitations && r.limitations.length > 0 && (
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
              {r.limitations.map((l, i) => (
                <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12.5, color: c.sub }}>
                  <Info size={14} style={{ color: c.info, flexShrink: 0, marginTop: 1 }} />
                  <span>{l.statement} <span style={{ color: c.info, fontWeight: 600 }}>(declared limitation)</span></span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
