"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ShieldCheck, ShieldAlert, Upload, RefreshCw, Loader2, ExternalLink, X } from "lucide-react";
import { staffToken, getPortalToken } from "@/lib/backendClient";

type Variant = "dark" | "light";

interface Dest {
  id: string; campaign: string; ad_group: string; final_url: string;
  cost_per_day: number | null; status: string; response_ms: number | null;
  last_checked_at: string | null; breach_since: string | null;
}
interface Campaign { name: string; total: number; broken: number; unverifiable: number; destinations: Dest[]; }
interface Guard {
  total: number; checked: number; ok: number; broken: number; unverifiable: number;
  all_clear: boolean; empty: boolean; last_checked: string | null; has_cost: boolean;
  breaches: Dest[]; spend: { daily_at_risk: number | null; since_detected: number | null };
  campaigns: Campaign[];
}
interface Preview { count: number; campaigns: string[]; has_cost: boolean; skipped: number; warnings: string[]; }

const T = {
  dark: { ink: "var(--text-primary)", sub: "var(--text-secondary)", muted: "var(--text-muted)",
    card: "var(--surface-card)", raised: "var(--surface-raised)", line: "var(--border-subtle)",
    brand: "var(--signal)", good: "#4caf7d", warn: "#f5a623", bad: "#e05c5c", badbg: "rgba(224,92,92,0.12)" },
  light: { ink: "#1c1a2e", sub: "#55506b", muted: "#928da6",
    card: "#ffffff", raised: "#f4f3f9", line: "#e7e4f0",
    brand: "var(--signal)", good: "#16a34a", warn: "#d97706", bad: "#dc2626", badbg: "#fef2f2" },
};

function useCountUp(target: number, ms = 600) {
  const [v, setV] = useState(0); const ref = useRef(0);
  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setV(target); return; }
    const from = ref.current, start = performance.now(); let raf = 0;
    const tick = (now: number) => { const t = Math.min(1, (now - start) / ms);
      const cur = Math.round(from + (target - from) * (1 - Math.pow(1 - t, 4))); setV(cur); ref.current = cur;
      if (t < 1) raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick); return () => cancelAnimationFrame(raf);
  }, [target, ms]); return v;
}

function midTrunc(url: string, head = 32, tail = 20): string {
  const u = (url || "").replace(/^https?:\/\//, "");
  if (u.length <= head + tail + 1) return u;
  return u.slice(0, head) + "…" + u.slice(-tail);
}
function latencyColor(ms: number | null, c: typeof T.dark): string {
  if (ms == null) return c.muted;
  if (ms < 300) return c.good; if (ms < 1000) return c.warn; return c.bad;
}
function statusLabel(s: string): { word: string; kind: "good" | "bad" | "muted" } {
  if (s === "ok") return { word: "Live", kind: "good" };
  if (s === "broken") return { word: "Dead page", kind: "bad" };
  if (s === "unverifiable") return { word: "Unverifiable", kind: "muted" };
  return { word: "Not checked yet", kind: "muted" };
}
function ago(iso: string | null): string {
  if (!iso) return "never";
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 90) return "just now"; if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`; return `${Math.floor(s / 86400)}d ago`;
}

export default function AdsWasteGuard({ variant, siteId, portal, canManage }:
  { variant: Variant; siteId?: string; portal?: boolean; canManage?: boolean }) {
  const c = T[variant];
  const [guard, setGuard] = useState<Guard | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [pendingCsv, setPendingCsv] = useState<string>("");
  const [busy, setBusy] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const token = portal ? getPortalToken() : await staffToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [portal]);

  const load = useCallback(async () => {
    try {
      const url = portal ? "/api/portal/ads" : `/api/sites/${siteId}/ads`;
      const res = await fetch(url, { headers: await authHeaders() });
      setGuard(await res.json());
    } catch { setGuard(null); }
  }, [portal, siteId, authHeaders]);

  useEffect(() => { load(); }, [load]);

  const onFile = async (file: File) => {
    setErr(null);
    const text = await file.text();
    setBusy("preview");
    try {
      const res = await fetch(`/api/sites/${siteId}/ads/preview`, {
        method: "POST", body: text, headers: { ...(await authHeaders()), "Content-Type": "text/csv" } });
      const p: Preview = await res.json();
      if (!p.count) { setErr(p.warnings?.[0] || "No ad destinations found in that file."); setBusy(""); return; }
      setPreview(p); setPendingCsv(text);
    } catch { setErr("Couldn't read that file."); } finally { setBusy(""); }
  };

  const commitImport = async () => {
    setBusy("import"); setErr(null);
    try {
      const res = await fetch(`/api/sites/${siteId}/ads/import`, {
        method: "POST", body: pendingCsv, headers: { ...(await authHeaders()), "Content-Type": "text/csv" } });
      const j = await res.json();
      if (!res.ok) throw new Error(j.error || "Import failed.");
      setPreview(null); setPendingCsv(""); await load();
    } catch (e) { setErr(e instanceof Error ? e.message : "Import failed."); } finally { setBusy(""); }
  };

  const verifyNow = async () => {
    setBusy("verify"); setErr(null);
    try {
      const res = await fetch(`/api/sites/${siteId}/ads/verify-now`, { method: "POST", headers: await authHeaders() });
      setGuard(await res.json());
    } catch { setErr("Verification failed."); } finally { setBusy(""); }
  };

  const money = (n: number | null | undefined) => n == null ? "" : `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  const verifiedCount = useCountUp(guard?.checked ?? 0);

  // ── Header ──
  const header = (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <ShieldCheck size={18} style={{ color: c.brand }} />
        <span style={{ fontFamily: "var(--font-stack-display)", fontWeight: 700, fontSize: 18, color: c.ink }}>Ad destinations</span>
      </div>
      {canManage && siteId && (
        <div style={{ display: "flex", gap: 8 }}>
          {guard && guard.total > 0 && (
            <button onClick={verifyNow} disabled={!!busy} style={ghostBtn(c, busy)}>
              {busy === "verify" ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} Verify now
            </button>
          )}
          <button onClick={() => fileRef.current?.click()} disabled={!!busy} style={primaryBtn(c, busy)}>
            <Upload size={14} /> Import CSV
          </button>
          <input ref={fileRef} type="file" accept=".csv,text/csv" style={{ display: "none" }}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
        </div>
      )}
    </div>
  );

  if (guard === null) {
    return <div>{header}<div className="animate-pulse" style={{ height: 140, borderRadius: 14, background: c.raised, border: `1px solid ${c.line}` }} /></div>;
  }

  return (
    <div onDragOver={(e) => { if (canManage) { e.preventDefault(); setDrag(true); } }}
         onDragLeave={() => setDrag(false)}
         onDrop={(e) => { if (!canManage) return; e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) onFile(f); }}>
      {header}
      {err && <div style={{ color: c.bad, fontSize: 13, marginBottom: 12 }}>{err}</div>}

      {/* Parsed-preview confirm step */}
      {preview && (
        <div style={{ border: `1px solid ${c.brand}`, borderRadius: 14, padding: 18, marginBottom: 16, background: c.raised }}>
          <div style={{ fontSize: 15, color: c.ink, fontWeight: 600 }}>
            Found <b style={{ color: c.brand }}>{preview.count}</b> destination{preview.count === 1 ? "" : "s"} across <b>{preview.campaigns.length}</b> campaign{preview.campaigns.length === 1 ? "" : "s"}
            {preview.has_cost ? " · cost included" : " · no cost column (spend hidden)"}.
          </div>
          {preview.skipped > 0 && <div style={{ color: c.muted, fontSize: 12.5, marginTop: 4 }}>{preview.skipped} unreadable row{preview.skipped === 1 ? "" : "s"} skipped.</div>}
          <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
            <button onClick={commitImport} disabled={!!busy} style={primaryBtn(c, busy)}>
              {busy === "import" ? <Loader2 size={14} className="animate-spin" /> : null} Import {preview.count}
            </button>
            <button onClick={() => { setPreview(null); setPendingCsv(""); }} style={ghostBtn(c, "")}>Cancel</button>
          </div>
        </div>
      )}

      {/* BREACH BANNER — full-width, above everything */}
      {guard.breaches.length > 0 && (
        <div style={{ borderRadius: 14, padding: "18px 20px", marginBottom: 16,
          background: c.badbg, border: `1px solid ${c.bad}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, color: c.bad, fontWeight: 800, fontSize: 15, fontFamily: "var(--font-stack-display)" }}>
            <ShieldAlert size={20} /> LIVE AD → DEAD PAGE
          </div>
          {guard.breaches.map((b) => (
            <div key={b.id} style={{ marginTop: 10, paddingTop: 10, borderTop: `1px solid ${c.line}` }}>
              <div style={{ color: c.ink, fontWeight: 600, fontSize: 14 }}>{b.campaign}{b.ad_group ? ` / ${b.ad_group}` : ""}</div>
              <a href={b.final_url} target="_blank" rel="noreferrer" style={{ color: c.sub, fontSize: 13, fontFamily: "var(--font-stack-mono)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 5, marginTop: 2 }}>
                {midTrunc(b.final_url)} <ExternalLink size={12} />
              </a>
              {guard.has_cost && b.cost_per_day != null && (
                <div style={{ color: c.bad, fontSize: 13, marginTop: 4, fontFamily: "var(--font-stack-mono)" }}>
                  ≈ {money(b.cost_per_day)}/day of spend hitting a dead page
                  {guard.spend.since_detected != null && <> · {money(guard.spend.since_detected)} since detected</>}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ALL-CLEAR HERO */}
      {guard.all_clear && (
        <div style={{ borderRadius: 14, padding: "28px 24px", marginBottom: 16, background: c.raised, border: `1px solid ${c.line}`, textAlign: "center" }}>
          <ShieldCheck size={30} style={{ color: c.good, marginBottom: 10 }} />
          <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 26, fontWeight: 800, color: c.ink }}>
            All <span style={{ fontFamily: "var(--font-stack-mono)", color: c.brand }}>{verifiedCount}</span> ad destinations verified
          </div>
          <div style={{ color: c.sub, fontSize: 13.5, marginTop: 6 }}>Last checked {ago(guard.last_checked)}
            {guard.unverifiable > 0 && ` · ${guard.unverifiable} unverifiable`}</div>
        </div>
      )}

      {/* EMPTY STATE */}
      {guard.empty && !preview && (
        <div style={{ border: `1px dashed ${drag ? c.brand : c.line}`, borderRadius: 16, padding: "40px 24px", textAlign: "center", background: drag ? c.raised : "transparent" }}>
          <Upload size={28} style={{ color: c.brand, marginBottom: 12 }} />
          <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 17, fontWeight: 600, color: c.ink }}>
            {canManage ? "Import your Google Ads final-URL export" : "No ad destinations imported yet"}
          </div>
          <div style={{ color: c.sub, fontSize: 14, marginTop: 6, maxWidth: 420, marginInline: "auto" }}>
            {canManage ? "Drag a CSV here or use Import — we verify every live ad's destination daily so spend never hits a dead page."
                       : "Your agency will import your campaigns' destinations here — then every live ad is checked daily."}
          </div>
        </div>
      )}

      {/* CAMPAIGN GROUPS (quiet when healthy, breached first) */}
      {!guard.empty && guard.campaigns.map((camp) => (
        <div key={camp.name} style={{ marginBottom: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: c.ink, textTransform: "uppercase", letterSpacing: "0.05em" }}>{camp.name}</span>
            {camp.broken > 0 && <span style={{ fontSize: 11, fontWeight: 700, color: c.bad, background: c.badbg, padding: "2px 8px", borderRadius: 999 }}>{camp.broken} dead</span>}
            <span style={{ fontSize: 12, color: c.muted }}>{camp.total} destination{camp.total === 1 ? "" : "s"}</span>
          </div>
          <div style={{ border: `1px solid ${c.line}`, borderRadius: 12, overflow: "hidden" }}>
            {camp.destinations.map((d, i) => {
              const sl = statusLabel(d.status);
              const dotColor = sl.kind === "good" ? c.good : sl.kind === "bad" ? c.bad : c.muted;
              return (
                <div key={d.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 14px",
                  borderTop: i ? `1px solid ${c.line}` : "none", background: d.status === "broken" ? c.badbg : c.card }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: dotColor, flexShrink: 0 }} />
                  <a href={d.final_url} target="_blank" rel="noreferrer" title={d.final_url}
                    style={{ flex: 1, minWidth: 0, color: c.ink, fontSize: 13, fontFamily: "var(--font-stack-mono)", textDecoration: "none", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {midTrunc(d.final_url)}
                  </a>
                  <span style={{ fontSize: 12, color: dotColor, fontWeight: 600, flexShrink: 0, width: 96, textAlign: "right" }}>{sl.word}</span>
                  <span style={{ fontSize: 12, color: latencyColor(d.response_ms, c), fontFamily: "var(--font-stack-mono)", flexShrink: 0, width: 60, textAlign: "right" }}>
                    {d.response_ms != null ? `${d.response_ms}ms` : "—"}
                  </span>
                  <span style={{ fontSize: 12, color: c.muted, flexShrink: 0, width: 72, textAlign: "right" }}>{ago(d.last_checked_at)}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* Spend footnote (only with imported cost) */}
      {!guard.empty && guard.has_cost && guard.spend.daily_at_risk != null && guard.spend.daily_at_risk > 0 && (
        <div style={{ color: c.muted, fontSize: 12, marginTop: 8 }}>
          Spend figures are from your imported Ads cost data.
        </div>
      )}
    </div>
  );
}

function primaryBtn(c: typeof T.dark, busy: string): React.CSSProperties {
  return { display: "inline-flex", alignItems: "center", gap: 7, background: c.brand, color: "#fff", border: "none",
    borderRadius: 9, padding: "8px 14px", fontSize: 13, fontWeight: 600, cursor: busy ? "wait" : "pointer", opacity: busy ? 0.7 : 1 };
}
function ghostBtn(c: typeof T.dark, busy: string): React.CSSProperties {
  return { display: "inline-flex", alignItems: "center", gap: 7, background: "transparent", color: c.sub,
    border: `1px solid ${c.line}`, borderRadius: 9, padding: "8px 14px", fontSize: 13, fontWeight: 600, cursor: busy ? "wait" : "pointer" };
}
