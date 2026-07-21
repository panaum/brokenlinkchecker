"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, Upload, Ghost, ArrowRight, Loader2, FileSearch, ServerCog, Clock, X, Check } from "lucide-react";
import { staffToken, getPortalToken } from "@/lib/backendClient";

type Variant = "dark" | "light";

interface Measured { url: string; hits: number; tier: string; source: string; top_referrers: string[]; priority?: string; reason?: string; }
interface Estimated { url: string; priority?: string; reason?: string; anchor_text?: string; }
interface GhostRow { url: string; hits: number; tier: string; severity: string; source: string; top_referrers: string[]; consequence: string; }
interface Triage {
  has_import: boolean; source: string | null; verdict: string | null;
  measured: Measured[]; estimated: Estimated[]; ghosts: GhostRow[];
  measured_count: number; ghost_count: number; top3_pct: number; total_hits: number;
  stale?: boolean; imported_at?: string | null;
}

const T = {
  dark: { ink: "var(--text-primary)", sub: "var(--text-secondary)", muted: "var(--text-muted)", card: "var(--surface-card)", raised: "var(--surface-raised)", line: "var(--border-subtle)", brand: "var(--signal)", neutral: "var(--status-neutral)", amber: "var(--status-attention)", ghostbg: "rgba(79,70,229,0.08)" },
  light: { ink: "#1c1a2e", sub: "#55506b", muted: "#928da6", card: "#ffffff", raised: "#f4f3f9", line: "#e7e4f0", brand: "var(--signal)", neutral: "#9aa0ac", amber: "#d97706", ghostbg: "#faf8fd" },
};

function useCountUp(target: number, ms = 550) {
  const [v, setV] = useState(0); const ref = useRef(0);
  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setV(target); return; }
    const from = ref.current, start = performance.now(); let raf = 0;
    const tick = (n: number) => { const t = Math.min(1, (n - start) / ms); const cur = Math.round(from + (target - from) * (1 - Math.pow(1 - t, 4))); setV(cur); ref.current = cur; if (t < 1) raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick); return () => cancelAnimationFrame(raf);
  }, [target, ms]); return v;
}
const mid = (u: string, h = 30, t = 18) => { const s = (u || "").replace(/^https?:\/\//, ""); return s.length <= h + t + 1 ? s : s.slice(0, h) + "…" + s.slice(-t); };
const logW = (hits: number, max: number) => max <= 0 ? 0 : Math.max(3, (Math.log(hits + 1) / Math.log(max + 1)) * 100);
const HitCount = ({ n, color }: { n: number; color: string }) => <span style={{ fontFamily: "var(--font-stack-mono)", fontWeight: 800, color, fontVariantNumeric: "tabular-nums" }}>{useCountUp(n)}</span>;
const srcChip = (s: string) => s === "gsc" ? "Googlebot · GSC" : "server log";
const srcTitle = (s: string) => s === "gsc" ? "GSC = how often Google's crawler hit this dead page — bot demand, not human visits." : "From your server 404 log — real human requests.";

export default function InboundTriage({ variant, siteId, portal, canManage }: { variant: Variant; siteId: string; portal?: boolean; canManage?: boolean }) {
  const c = T[variant];
  const [d, setD] = useState<Triage | null>(null);
  const [preview, setPreview] = useState<{ count: number; total_hits: number; source: string; records: Array<{ url_normalized: string; hits: number }> } | null>(null);
  const [pendingCsv, setPendingCsv] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const auth = useCallback(async (): Promise<Record<string, string>> => {
    const t = portal ? getPortalToken() : await staffToken();
    return t ? { Authorization: `Bearer ${t}` } : {};
  }, [portal]);
  const load = useCallback(async () => {
    try { const res = await fetch(`/api/sites/${siteId}/inbound-404/triage`, { headers: await auth() }); setD(await res.json()); } catch { setD(null); }
  }, [siteId, auth]);
  useEffect(() => { load(); }, [load]);

  const onFile = async (f: File) => {
    setErr(null); const text = await f.text(); setBusy("preview");
    try {
      const res = await fetch(`/api/sites/${siteId}/inbound-404/preview`, { method: "POST", body: text, headers: { ...(await auth()), "Content-Type": "text/csv" } });
      const p = await res.json();
      if (!p.count) { setErr(p.warnings?.[0] || "No dead URLs found in that file."); setBusy(""); return; }
      setPreview(p); setPendingCsv(text);
    } catch { setErr("Couldn't read that file."); } finally { setBusy(""); }
  };
  const commit = async () => {
    setBusy("import");
    try { await fetch(`/api/sites/${siteId}/inbound-404/import`, { method: "POST", body: pendingCsv, headers: { ...(await auth()), "Content-Type": "text/csv" } }); setPreview(null); setPendingCsv(""); await load(); }
    finally { setBusy(""); }
  };

  if (d === null) return <div className="animate-pulse" style={{ height: 220, borderRadius: 14, background: c.raised, border: `1px solid ${c.line}` }} />;

  const hidden = <input ref={fileRef} type="file" accept=".csv,text/csv" style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />;
  const header = (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Activity size={18} style={{ color: c.brand }} />
        <span style={{ fontFamily: "var(--font-stack-display)", fontWeight: 700, fontSize: 18, color: c.ink }}>Inbound-404 triage</span>
        {d.stale && <span title="Re-import to keep the ranking current" style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "rgba(217,119,6,0.12)", color: c.amber, fontSize: 11.5, padding: "2px 9px", borderRadius: 999 }}><Clock size={12} /> hit data is stale — re-import</span>}
      </div>
      {canManage && !portal && d.has_import && <button onClick={() => fileRef.current?.click()} style={btn(c.brand, "#fff", busy)}><Upload size={14} /> Re-import</button>}
      {hidden}
    </div>
  );

  // ── Parsed-preview: a mini demand chart, payoff before commit ──
  if (preview) {
    const max = Math.max(...preview.records.map((r) => r.hits), 1);
    return <div>{header}
      <div style={{ border: `1px solid ${c.brand}`, borderRadius: 14, padding: 18, background: c.raised }}>
        <div style={{ fontSize: 15, color: c.ink, fontWeight: 600 }}>Found <b style={{ color: c.brand }}>{preview.total_hits}</b> {preview.source === "gsc" ? "crawl hits" : "hits"} across <b>{preview.count}</b> dead URL{preview.count === 1 ? "" : "s"} — import?</div>
        <div style={{ margin: "14px 0", display: "flex", flexDirection: "column", gap: 5 }}>
          {preview.records.slice(0, 8).map((r, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ flex: 1, minWidth: 0, height: 18, background: c.card, borderRadius: 4, overflow: "hidden" }}>
                <div style={{ width: `${logW(r.hits, max)}%`, height: "100%", background: i < 3 ? c.brand : c.neutral, borderRadius: 4 }} />
              </div>
              <span style={{ fontFamily: "var(--font-stack-mono)", fontSize: 12, color: c.sub, width: 44, textAlign: "right" }}>{r.hits}</span>
              <span style={{ fontFamily: "var(--font-stack-mono)", fontSize: 11.5, color: c.muted, width: 200, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{mid(r.url_normalized, 26, 14)}</span>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={commit} disabled={!!busy} style={btn(c.brand, "#fff", busy)}>{busy === "import" ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Import {preview.count}</button>
          <button onClick={() => { setPreview(null); setPendingCsv(""); }} style={btn("transparent", c.sub, "", c.line)}>Cancel</button>
        </div>
      </div>
    </div>;
  }

  // ── Pre-import invitation (day one) ──
  if (!d.has_import) {
    return <div>{header}
      {!portal && (
        <div style={{ border: `1px solid ${c.line}`, borderRadius: 16, padding: "22px 24px", background: c.raised, marginBottom: 16 }}>
          <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 18, fontWeight: 700, color: c.ink }}>This ranking is estimated.</div>
          <div style={{ color: c.sub, fontSize: 13.5, marginTop: 5, marginBottom: 16 }}>Import your 404 logs or Google Search Console crawl errors to rank by <b style={{ color: c.ink }}>real visitor demand</b> — takes 2 minutes.</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px,1fr))", gap: 12 }}>
            <button onClick={() => fileRef.current?.click()} style={importCard(c)}>
              <FileSearch size={20} style={{ color: c.brand }} /><div style={{ fontWeight: 600, color: c.ink, fontSize: 14 }}>GSC crawl errors</div><div style={{ color: c.muted, fontSize: 12 }}>Googlebot demand · export from Search Console</div>
            </button>
            <button onClick={() => fileRef.current?.click()} style={importCard(c)}>
              <ServerCog size={20} style={{ color: c.brand }} /><div style={{ fontWeight: 600, color: c.ink, fontSize: 14 }}>Server 404 log</div><div style={{ color: c.muted, fontSize: 12 }}>Human visits · Apache/Nginx CSV with hit counts</div>
            </button>
          </div>
        </div>
      )}
      {hidden}
      <EstimatedList rows={d.estimated} c={c} label="Current estimated ranking" />
    </div>;
  }

  // ── Full triage: verdict + demand chart + measured/estimated + ghosts ──
  const bars = [...d.measured.map((m) => ({ url: m.url, hits: m.hits, ghost: false })),
                ...d.ghosts.map((g) => ({ url: g.url, hits: g.hits, ghost: true }))].sort((a, b) => b.hits - a.hits);
  const max = Math.max(...bars.map((b) => b.hits), 1);

  return <div>{header}
    {/* VERDICT HERO */}
    {d.verdict && <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 23, fontWeight: 800, lineHeight: 1.28, color: c.ink, textWrap: "balance" as "balance", marginBottom: 18 }}>{d.verdict}</div>}

    {/* THE DEMAND CHART — the seismograph */}
    {bars.length > 0 && (
      <div style={{ border: `1px solid ${c.line}`, borderRadius: 14, padding: "16px 18px", background: c.card, marginBottom: 18 }}>
        <div style={{ fontSize: 11, color: c.muted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12 }}>Where visitors hit walls — by measured demand</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
          {bars.slice(0, 12).map((b, i) => (
            <div key={i} className="demand-bar-row" style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontFamily: "var(--font-stack-mono)", fontSize: 11, color: c.muted, width: 20, textAlign: "right" }}>{i + 1}</span>
              <div style={{ flex: 1, minWidth: 0, height: 22, background: c.raised, borderRadius: 5, overflow: "hidden", position: "relative" }}>
                <div className="demand-bar" style={{ width: `${logW(b.hits, max)}%`, height: "100%", background: i < 3 ? c.brand : c.neutral, borderRadius: 5, transition: "width 220ms ease", transitionDelay: `${i * 20}ms` }} />
                <span style={{ position: "absolute", left: 10, top: 0, height: "100%", display: "flex", alignItems: "center", fontFamily: "var(--font-stack-mono)", fontSize: 11.5, color: i < 3 ? "#fff" : c.ink, whiteSpace: "nowrap" }} title={b.url}>{mid(b.url, 32, 16)}{b.ghost ? " 👻" : ""}</span>
              </div>
              <span style={{ fontFamily: "var(--font-stack-mono)", fontSize: 14, fontWeight: 700, color: i < 3 ? c.brand : c.ink, width: 52, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{b.hits}</span>
            </div>
          ))}
        </div>
      </div>
    )}

    {/* MEASURED rows (heavy) */}
    {d.measured.length > 0 && <div style={{ marginBottom: 18 }}>
      <SectionLabel c={c}>Measured — ranked by real demand</SectionLabel>
      <div style={{ border: `1px solid ${c.line}`, borderRadius: 12, overflow: "hidden" }}>
        {d.measured.map((m, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 14px", borderTop: i ? `1px solid ${c.line}` : "none", background: c.card }}>
            <div style={{ width: 90, flexShrink: 0 }}>
              <div style={{ height: 8, background: c.raised, borderRadius: 4, overflow: "hidden" }}><div style={{ width: `${logW(m.hits, max)}%`, height: "100%", background: c.brand }} /></div>
            </div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <a href={m.url} target="_blank" rel="noreferrer" title={m.url} style={{ color: c.ink, fontSize: 13.5, fontFamily: "var(--font-stack-mono)", textDecoration: "none", fontWeight: 600 }}>{mid(m.url)}</a>
              <div style={{ display: "flex", gap: 6, marginTop: 3, alignItems: "center" }}>
                <span title={srcTitle(m.source)} style={{ fontSize: 10.5, color: c.sub, border: `1px solid ${c.line}`, padding: "1px 7px", borderRadius: 999, cursor: "help" }}>{srcChip(m.source)}</span>
                <span style={{ fontSize: 11, color: c.muted }}>{m.tier.replace("-", " ")}</span>
              </div>
            </div>
            <div style={{ textAlign: "right", flexShrink: 0 }}>
              <div style={{ fontSize: 20 }}><HitCount n={m.hits} color={c.ink} /></div>
              <div style={{ fontSize: 10.5, color: c.muted }}>{m.source === "gsc" ? "crawl hits" : "hits"}</div>
            </div>
          </div>
        ))}
      </div>
    </div>}

    {/* ESTIMATED rows (light) */}
    {d.estimated.length > 0 && <div style={{ marginBottom: 18 }}>
      <SectionLabel c={c}>Estimated — no demand data for these</SectionLabel>
      <EstimatedList rows={d.estimated} c={c} bare />
    </div>}

    {/* 👻 GHOST TRAFFIC */}
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <Ghost size={17} style={{ color: c.brand }} />
        <span style={{ fontFamily: "var(--font-stack-display)", fontWeight: 700, fontSize: 16, color: c.ink }}>Dead ends only your visitors know about</span>
      </div>
      {d.ghosts.length === 0 ? (
        <div style={{ border: `1px dashed ${c.line}`, borderRadius: 14, padding: "30px 20px", textAlign: "center", background: c.raised }}>
          <div style={{ fontFamily: "var(--font-stack-mono)", fontSize: 40, fontWeight: 800, color: c.brand, lineHeight: 1 }}>0</div>
          <div style={{ color: c.ink, fontSize: 14, fontWeight: 600, marginTop: 8 }}>No ghost traffic — every URL visitors request exists ✓</div>
        </div>
      ) : <>
        <div style={{ color: c.sub, fontSize: 12.5, marginBottom: 10 }}>No page on your site links here — yet {d.ghosts.reduce((n, g) => n + g.hits, 0)} {d.source === "gsc" ? "crawl hits" : "people"} tried to reach these{d.source === "gsc" ? "" : " last import window"}.</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {d.ghosts.map((g, i) => (
            <div key={i} style={{ borderLeft: `3px dashed ${c.brand}`, border: `1px solid ${c.line}`, borderLeftWidth: 3, borderRadius: 10, padding: "12px 14px", background: c.ghostbg, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ color: c.ink, fontSize: 13.5, fontFamily: "var(--font-stack-mono)", fontWeight: 600 }} title={g.url}>{mid(g.url)}</div>
                <div style={{ color: c.sub, fontSize: 12, marginTop: 3 }}>{g.consequence}</div>
                {g.top_referrers.length > 0 && <div style={{ color: c.muted, fontSize: 11.5, marginTop: 4 }}>arriving from: {g.top_referrers.join(", ")}</div>}
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 18 }}><HitCount n={g.hits} color={c.brand} /></div>
                <div style={{ fontSize: 10.5, color: c.muted }}>{g.source === "gsc" ? "crawl hits" : "hits"}</div>
              </div>
              {canManage && !portal && <button onClick={async () => { await fetch(`/api/sites/${siteId}/inbound-404/redirect`, { method: "POST", headers: { ...(await auth()), "Content-Type": "application/json" }, body: JSON.stringify({ url: g.url }) }); }} style={btn(c.brand, "#fff", "")}>Add redirect <ArrowRight size={13} /></button>}
            </div>
          ))}
        </div>
      </>}
    </div>
  </div>;
}

function EstimatedList({ rows, c, label, bare }: { rows: Estimated[]; c: typeof T.dark; label?: string; bare?: boolean }) {
  const body = (
    <div style={{ border: `1px solid ${c.line}`, borderRadius: 12, overflow: "hidden" }}>
      {rows.slice(0, 20).map((r, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", borderTop: i ? `1px solid ${c.line}` : "none", background: c.card, opacity: 0.82 }}>
          <div style={{ width: 90, flexShrink: 0, display: "flex", alignItems: "center" }}>
            {/* the dotted rail where a measured bar would be */}
            <div style={{ flex: 1, borderTop: `1px dotted ${c.muted}`, opacity: 0.5 }} />
          </div>
          <a href={r.url} target="_blank" rel="noreferrer" title={r.url} style={{ flex: 1, minWidth: 0, color: c.sub, fontSize: 13, fontFamily: "var(--font-stack-mono)", textDecoration: "none", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{(r.url || "").replace(/^https?:\/\//, "")}</a>
          <span style={{ fontSize: 10.5, color: c.muted, border: `1px solid ${c.line}`, padding: "1px 7px", borderRadius: 999 }}>{r.priority || "low"}</span>
          <span style={{ fontSize: 11, color: c.muted, fontStyle: "italic" }}>estimated</span>
        </div>
      ))}
    </div>
  );
  if (bare) return body;
  return <div>{label && <SectionLabel c={c}>{label}</SectionLabel>}{body}</div>;
}
function SectionLabel({ children, c }: { children: React.ReactNode; c: typeof T.dark }) {
  return <div style={{ fontSize: 12, color: c.muted, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>{children}</div>;
}
function btn(bg: string, fg: string, busy: string, border?: string): React.CSSProperties {
  return { display: "inline-flex", alignItems: "center", gap: 6, background: bg, color: fg, border: border ? `1px solid ${border}` : "none", borderRadius: 9, padding: "8px 13px", fontSize: 13, fontWeight: 600, cursor: busy ? "wait" : "pointer", opacity: busy ? 0.7 : 1 };
}
function importCard(c: typeof T.dark): React.CSSProperties {
  return { display: "flex", flexDirection: "column", gap: 5, alignItems: "flex-start", textAlign: "left", background: c.card, border: `1px solid ${c.line}`, borderRadius: 12, padding: "16px 16px", cursor: "pointer" };
}
