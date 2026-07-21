"use client";

import { useCallback, useEffect, useState } from "react";
import { ScrollText, ShieldCheck, AlertTriangle, Info, Wrench, FileText, Loader2, Link2 } from "lucide-react";
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
  dark: { ink: "var(--text-primary)", sub: "var(--text-secondary)", muted: "var(--text-muted)", card: "var(--surface-card)", raised: "var(--surface-raised)", line: "var(--border-subtle)", brand: "var(--signal)", good: "#4caf7d", bad: "#e05c5c", high: "#f5a623", info: "#7a7a8c", badbg: "rgba(224,92,92,0.12)" },
  light: { ink: "#1c1a2e", sub: "#55506b", muted: "#928da6", card: "#ffffff", raised: "#f4f3f9", line: "#e7e4f0", brand: "var(--signal)", good: "#16a34a", bad: "#dc2626", high: "#ea580c", info: "#8a86a0", badbg: "#fef2f2" },
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

      {!portal && <AttestationShelf siteId={siteId} c={c} />}
    </div>
  );
}

function AttestationShelf({ siteId, c }: { siteId: string; c: typeof T.dark }) {
  const now = new Date();
  const defQ = `${now.getFullYear()}-Q${Math.floor(now.getMonth() / 3) + 1}`;
  const [quarter, setQuarter] = useState(defQ);
  const [list, setList] = useState<Array<{ id: string; period_label: string; content_hash: string; share_token: string; issued_at: string }>>([]);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState("");

  const staff = async (): Promise<Record<string, string>> => { const t = await staffToken(); return t ? { Authorization: `Bearer ${t}`, "Content-Type": "application/json" } : { "Content-Type": "application/json" }; };
  const load = useCallback(async () => {
    try { const r = await fetch(`/api/sites/${siteId}/attestations`, { headers: await staff() }); setList((await r.json()).attestations || []); } catch { setList([]); }
  }, [siteId]);
  useEffect(() => { load(); }, [load]);

  const generate = async () => {
    setBusy(true);
    try { await fetch(`/api/sites/${siteId}/attestation/generate`, { method: "POST", headers: await staff(), body: JSON.stringify({ quarter }) }); await load(); } finally { setBusy(false); }
  };
  const copyShare = (token: string) => { navigator.clipboard?.writeText(`${location.origin}/attest/${token}`); setCopied(token); setTimeout(() => setCopied(""), 1500); };

  return (
    <div style={{ marginTop: 24, paddingTop: 18, borderTop: `1px solid ${c.line}` }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10, marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <FileText size={16} style={{ color: c.brand }} />
          <span style={{ fontFamily: "var(--font-stack-display)", fontWeight: 700, fontSize: 15, color: c.ink }}>Quarterly attestation</span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input value={quarter} onChange={(e) => setQuarter(e.target.value)} placeholder="2026-Q2" data-gramm="false"
            style={{ width: 100, background: c.raised, border: `1px solid ${c.line}`, borderRadius: 8, padding: "7px 10px", fontSize: 13, color: c.ink }} />
          <button onClick={generate} disabled={busy} style={{ display: "inline-flex", alignItems: "center", gap: 6, background: c.brand, color: "#fff", border: "none", borderRadius: 8, padding: "7px 13px", fontSize: 13, fontWeight: 600, cursor: busy ? "wait" : "pointer" }}>
            {busy ? <Loader2 size={13} className="animate-spin" /> : <FileText size={13} />} Issue attestation
          </button>
        </div>
      </div>
      {list.length === 0 ? (
        <div style={{ color: c.muted, fontSize: 12.5 }}>No attestations issued yet. Issue one to hand to a client&apos;s legal or procurement team.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {list.map((a) => (
            <div key={a.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 12px", border: `1px solid ${c.line}`, borderRadius: 10, background: c.card }}>
              <span style={{ fontWeight: 600, color: c.ink, fontSize: 13 }}>{a.period_label}</span>
              <span style={{ color: c.muted, fontSize: 11, fontFamily: "var(--font-stack-mono)" }}>{a.content_hash.slice(0, 12)}…</span>
              <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                <a href={`/attestations/${a.id}`} target="_blank" rel="noreferrer" style={{ color: c.brand, fontSize: 12.5, textDecoration: "none", fontWeight: 600 }}>Open</a>
                <button onClick={() => copyShare(a.share_token)} style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "none", border: "none", color: c.sub, fontSize: 12.5, cursor: "pointer" }}>
                  <Link2 size={13} /> {copied === a.share_token ? "Copied" : "Share link"}
                </button>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
