"use client";

import { useCallback, useEffect, useState } from "react";
import { ShieldQuestion, Play, Loader2, AlertTriangle, Info } from "lucide-react";
import { staffToken, getPortalToken } from "@/lib/backendClient";

type Variant = "dark" | "light";

interface Req { host: string; url: string; class: string; provenance: string; ms_after_load?: number; }
interface Verdict { kind: string; regime: string; code: string; severity: string; statement: string; citation: string; }
interface Session {
  id: string; page_url: string; regime: string; mode: string; requests: Req[];
  cmp: { detected?: boolean; vendor?: string; operated?: boolean }; optout: Record<string, unknown>;
  verdicts: Verdict[]; engine_version: number; classification_version: number; created_at: string;
}
interface Data { scope_statement: string; sessions: Session[]; }

const T = {
  dark: { ink: "var(--text-primary)", sub: "var(--text-secondary)", muted: "var(--text-muted)", card: "var(--surface-card)", raised: "var(--surface-raised)", line: "rgba(255,255,255,0.08)", brand: "#a855f7", bad: "#f87171", high: "#fb923c", info: "#8b93a7", badbg: "rgba(248,113,113,0.12)" },
  light: { ink: "#1c1a2e", sub: "#55506b", muted: "#928da6", card: "#ffffff", raised: "#f4f3f9", line: "#e7e4f0", brand: "#7c3aed", bad: "#dc2626", high: "#ea580c", info: "#8a86a0", badbg: "#fef2f2" },
};
const classColor = (cls: string, c: typeof T.dark) => cls === "advertising-adtech" ? c.bad : cls === "analytics" ? c.high : cls === "essential" ? c.info : c.sub;
const sev = (s: string, c: typeof T.dark) => s === "critical" ? c.bad : s === "high" ? c.high : c.info;
const fmt = (iso: string) => new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

export default function ConsentSessions({ variant, siteId, portal, canManage }: { variant: Variant; siteId: string; portal?: boolean; canManage?: boolean }) {
  const c = T[variant];
  const [d, setD] = useState<Data | null>(null);
  const [url, setUrl] = useState("");
  const [regime, setRegime] = useState("BOTH");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const auth = useCallback(async (): Promise<Record<string, string>> => {
    const t = portal ? getPortalToken() : await staffToken();
    return t ? { Authorization: `Bearer ${t}`, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
  }, [portal]);

  const load = useCallback(async () => {
    try { const res = await fetch(`/api/sites/${siteId}/consent/sessions`, { headers: await auth() }); setD(await res.json()); } catch { setD(null); }
  }, [siteId, auth]);
  useEffect(() => { load(); }, [load]);

  const run = async () => {
    if (!url.trim()) return;
    setBusy("run"); setMsg(null);
    try {
      await fetch(`/api/sites/${siteId}/consent/enroll`, { method: "POST", headers: await auth(), body: JSON.stringify({ page_url: url.trim(), regime }) });
      const r = await fetch(`/api/sites/${siteId}/consent/run`, { method: "POST", headers: await auth(), body: JSON.stringify({ page_url: url.trim(), regime }) });
      const j = await r.json();
      setMsg(r.ok ? `Recorded ${j.sessions} session(s) · ${j.observations} observation(s).` : (j.error || "Run failed."));
      await load();
    } catch { setMsg("Run failed."); } finally { setBusy(""); }
  };

  if (d === null) return <div className="animate-pulse" style={{ height: 160, borderRadius: 14, background: c.raised, border: `1px solid ${c.line}` }} />;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <ShieldQuestion size={18} style={{ color: c.brand }} />
          <span style={{ fontFamily: "var(--font-stack-display)", fontWeight: 700, fontSize: 18, color: c.ink }}>Consent behavior — observation ledger</span>
        </div>
      </div>
      {/* The wording law — scope statement always visible on every surface */}
      <div style={{ color: c.muted, fontSize: 12, marginBottom: 14, fontStyle: "italic" }}>{d.scope_statement}</div>

      {canManage && !portal && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://client.com/landing" data-gramm="false"
            style={{ flex: 1, minWidth: 240, background: c.raised, border: `1px solid ${c.line}`, borderRadius: 9, padding: "8px 12px", fontSize: 13, color: c.ink }} />
          <select value={regime} onChange={(e) => setRegime(e.target.value)} style={{ background: c.raised, border: `1px solid ${c.line}`, borderRadius: 9, padding: "8px 12px", fontSize: 13, color: c.ink }}>
            <option value="BOTH">UK + US</option><option value="UK">UK (PECR)</option><option value="US">US (GPC)</option>
          </select>
          <button onClick={run} disabled={!!busy} style={{ display: "inline-flex", alignItems: "center", gap: 7, background: c.brand, color: "#fff", border: "none", borderRadius: 9, padding: "8px 14px", fontSize: 13, fontWeight: 600, cursor: busy ? "wait" : "pointer" }}>
            {busy === "run" ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} Enroll &amp; observe
          </button>
        </div>
      )}
      {msg && <div style={{ fontSize: 12.5, color: c.sub, marginBottom: 12 }}>{msg}</div>}

      {d.sessions.length === 0 ? (
        <div style={{ border: `1px dashed ${c.line}`, borderRadius: 14, padding: "32px 20px", textAlign: "center", background: c.raised, color: c.sub, fontSize: 13.5 }}>
          No sessions recorded yet. The ledger begins recording at enrollment — earlier behaviour cannot be reconstructed.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {d.sessions.map((s) => (
            <div key={s.id} style={{ border: `1px solid ${c.line}`, borderRadius: 12, background: c.card, overflow: "hidden" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", borderBottom: `1px solid ${c.line}`, flexWrap: "wrap" }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: c.brand, textTransform: "uppercase", letterSpacing: "0.05em" }}>{s.regime} · {s.mode}</span>
                <span style={{ color: c.sub, fontSize: 12 }}>{s.page_url.replace(/^https?:\/\//, "")}</span>
                <span style={{ color: c.muted, fontSize: 11.5, marginLeft: "auto" }}>{fmt(s.created_at)} · engine v{s.engine_version} · table v{s.classification_version}</span>
              </div>
              {/* Verdicts (observations + declared limitations) */}
              {s.verdicts.length > 0 && (
                <div style={{ padding: "10px 14px", display: "flex", flexDirection: "column", gap: 6, borderBottom: `1px solid ${c.line}`, background: s.verdicts.some((v) => v.kind === "observation") ? c.badbg : "transparent" }}>
                  {s.verdicts.map((v, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12.5 }}>
                      {v.kind === "observation" ? <AlertTriangle size={14} style={{ color: sev(v.severity, c), flexShrink: 0, marginTop: 1 }} /> : <Info size={14} style={{ color: c.info, flexShrink: 0, marginTop: 1 }} />}
                      <div>
                        <span style={{ color: c.ink }}>{v.statement}</span>
                        {v.citation && <span style={{ color: c.muted }}> — {v.citation}</span>}
                        {v.kind === "limitation" && <span style={{ color: c.info, fontWeight: 600 }}> (declared limitation)</span>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {/* Raw request list with class + timing */}
              {s.requests.length > 0 && (
                <div style={{ padding: "8px 14px" }}>
                  {s.requests.slice(0, 8).map((r, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "4px 0", fontSize: 12 }}>
                      <span style={{ width: 8, height: 8, borderRadius: 2, background: classColor(r.class, c), flexShrink: 0 }} />
                      <span style={{ flex: 1, minWidth: 0, color: c.ink, fontFamily: "var(--font-stack-mono)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.host}</span>
                      <span style={{ color: classColor(r.class, c), fontSize: 11 }}>{r.class}</span>
                      {r.ms_after_load != null && <span style={{ color: c.muted, fontFamily: "var(--font-stack-mono)", fontSize: 11, width: 60, textAlign: "right" }}>+{r.ms_after_load}ms</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
