"use client";

import { useCallback, useEffect, useState } from "react";
import { LineChart, Line, YAxis, XAxis, ResponsiveContainer, Tooltip } from "recharts";
import { Activity, Repeat, TrendingDown, Clock, Eye, EyeOff } from "lucide-react";
import { staffToken, getPortalToken } from "@/lib/backendClient";

type Variant = "dark" | "light";

interface Metrics { new_per_month: number; new_per_window: number; mttr_days: number | null; mtbb_days: number | null; recurrence_rate: number; funnel_share: number; distinct_pages: number; }
interface Recur { fingerprint: string; url: string; zone: string; count: number; }
interface Frag {
  insufficient?: boolean; gate?: { reason: string; have_days: number | null; have_scans: number | null };
  score: number; band: string; factors: string[]; metrics: Metrics;
  trend: Array<{ at: string; score: number }>; recurrence: Recur[];
  suggestion: { suggest_freq: string; current: string; text: string; evidence: string } | null;
  client_visible: boolean;
}

const T = {
  dark: { ink: "var(--text-primary)", sub: "var(--text-secondary)", muted: "var(--text-muted)", card: "var(--surface-card)", raised: "var(--surface-raised)", line: "rgba(255,255,255,0.08)", brand: "#a855f7", good: "#4ade80", warn: "#fbbf24", bad: "#f87171", badbg: "rgba(248,113,113,0.12)" },
  light: { ink: "#1c1a2e", sub: "#55506b", muted: "#928da6", card: "#ffffff", raised: "#f4f3f9", line: "#e7e4f0", brand: "#7c3aed", good: "#16a34a", warn: "#d97706", bad: "#dc2626", badbg: "#fef2f2" },
};
const bandColor = (b: string, c: typeof T.dark) => b === "brittle" ? c.bad : b === "sturdy" ? c.good : c.warn;
const bandWord = (b: string) => b === "brittle" ? "Brittle" : b === "sturdy" ? "Sturdy" : "Normal";
const dstr = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function verdict(f: Frag): string {
  const m = f.metrics;
  if (f.band === "sturdy") return "This site is sturdy — it rarely breaks.";
  const weeks = m.mtbb_days ? Math.max(1, Math.round(m.mtbb_days / 7)) : null;
  const cadence = weeks ? `it breaks about every ${weeks === 1 ? "week" : `${weeks} weeks`}` : "it breaks periodically";
  const funnel = m.funnel_share >= 0.6 ? ", almost always in funnel pages" : "";
  const lead = f.band === "brittle" ? "This site is brittle" : "This site breaks occasionally";
  return `${lead} — ${cadence}${funnel}.`;
}

// ── Portal: positive improvement story only ──
function PortalImprovement({ siteId, c }: { siteId: string; c: typeof T.dark }) {
  const [d, setD] = useState<{ visible: boolean; improvement_pct?: number; text?: string; trend?: Array<{ at: string; stability: number }> } | null>(null);
  useEffect(() => { (async () => {
    try { const t = getPortalToken(); const r = await fetch(`/api/sites/${siteId}/fragility/client`, { headers: t ? { Authorization: `Bearer ${t}` } : {} }); setD(await r.json()); } catch { setD({ visible: false }); }
  })(); }, [siteId]);
  if (!d || !d.visible) return null;
  return (
    <div className="ds-card ds-card-pad" style={{ marginTop: "var(--space-5)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <TrendingDown size={18} style={{ color: c.good }} />
        <span style={{ fontFamily: "var(--font-stack-display)", fontWeight: 700, fontSize: 18, color: c.ink }}>Stability</span>
      </div>
      <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 22, fontWeight: 800, color: c.ink }}>{d.text}</div>
      {d.trend && <div style={{ height: 120, marginTop: 12 }}>
        <ResponsiveContainer width="100%" height="100%"><LineChart data={d.trend}>
          <YAxis domain={[0, 100]} hide /><Line type="monotone" dataKey="stability" stroke={c.good} strokeWidth={2.5} dot={false} isAnimationActive={false} />
        </LineChart></ResponsiveContainer>
      </div>}
    </div>
  );
}

export default function FragilityPanel({ variant, siteId, portal }: { variant: Variant; siteId: string; portal?: boolean }) {
  const c = T[variant];
  const [f, setF] = useState<Frag | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try { const t = await staffToken(); const r = await fetch(`/api/sites/${siteId}/fragility`, { headers: t ? { Authorization: `Bearer ${t}` } : {} }); setF(await r.json()); } catch { setF(null); }
  }, [siteId]);
  useEffect(() => { if (!portal) load(); }, [load, portal]);

  if (portal) return <PortalImprovement siteId={siteId} c={c} />;

  const heading = (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
      <Activity size={18} style={{ color: c.brand }} />
      <span style={{ fontFamily: "var(--font-stack-display)", fontWeight: 700, fontSize: 18, color: c.ink }}>Fragility</span>
    </div>
  );
  if (f === null) return <div>{heading}<div className="animate-pulse" style={{ height: 160, borderRadius: 14, background: c.raised, border: `1px solid ${c.line}` }} /></div>;

  if (f.insufficient) {
    return <div>{heading}<div style={{ border: `1px dashed ${c.line}`, borderRadius: 16, padding: "34px 24px", textAlign: "center", background: c.raised }}>
      <Clock size={26} style={{ color: c.muted, marginBottom: 10 }} />
      <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 17, fontWeight: 600, color: c.ink }}>Not enough history yet</div>
      <div style={{ color: c.sub, fontSize: 13.5, marginTop: 5 }}>{f.gate?.reason} (have {f.gate?.have_days ?? 0} days · {f.gate?.have_scans ?? 0} scans)</div>
    </div></div>;
  }

  const col = bandColor(f.band, c);
  const toggle = async () => {
    setSaving(true);
    try { const t = await staffToken(); await fetch(`/api/sites/${siteId}/fragility/visibility`, { method: "POST", headers: { ...(t ? { Authorization: `Bearer ${t}` } : {}), "Content-Type": "application/json" }, body: JSON.stringify({ client_visible: !f.client_visible }) }); await load(); } finally { setSaving(false); }
  };

  return (
    <div>{heading}
      {/* ── VERDICT ── */}
      <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 22, fontWeight: 800, lineHeight: 1.25, color: c.ink, textWrap: "balance" as "balance", marginBottom: 16 }}>{verdict(f)}</div>

      {/* ── SCORE CHIP + FACTORS (the factors rule — never a score without reasons) ── */}
      <div style={{ display: "flex", gap: 18, alignItems: "center", border: `1px solid ${col}`, background: f.band === "brittle" ? c.badbg : c.raised, borderRadius: 14, padding: "16px 20px", flexWrap: "wrap" }}>
        <div style={{ textAlign: "center", flexShrink: 0 }}>
          <div style={{ fontFamily: "var(--font-stack-mono)", fontSize: 40, fontWeight: 800, color: col, lineHeight: 1 }}>{f.score}</div>
          <div style={{ color: col, fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", marginTop: 4 }}>{bandWord(f.band)}</div>
        </div>
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ color: c.muted, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 5 }}>Because</div>
          <ul style={{ margin: 0, paddingLeft: 16, color: c.ink, fontSize: 13.5, display: "flex", flexDirection: "column", gap: 3 }}>
            {f.factors.map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        </div>
      </div>

      {/* ── STABILITY TREND (score over time) ── */}
      {f.trend.length >= 2 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <span style={{ fontSize: 12, color: c.muted, textTransform: "uppercase", letterSpacing: "0.05em" }}>Fragility since monitoring began</span>
            <span style={{ fontFamily: "var(--font-stack-mono)", fontSize: 13, color: f.trend[f.trend.length - 1].score <= f.trend[0].score ? c.good : c.bad }}>{f.trend[0].score} → {f.trend[f.trend.length - 1].score}</span>
          </div>
          <div style={{ height: 110, marginTop: 8 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={f.trend.map((t) => ({ x: dstr(t.at), score: t.score }))}>
                <XAxis dataKey="x" tick={{ fill: c.muted, fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={24} />
                <YAxis domain={[0, 100]} width={26} tick={{ fill: c.muted, fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: c.card, border: `1px solid ${c.line}`, borderRadius: 8, fontSize: 12 }} formatter={(v) => [`${v}`, "fragility"]} />
                <Line type="monotone" dataKey="score" stroke={c.brand} strokeWidth={2.5} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* ── RECURRENCE PATTERNS ── */}
      {f.recurrence && f.recurrence.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, color: c.muted, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>Fixes that aren't holding</div>
          {f.recurrence.slice(0, 4).map((r) => (
            <div key={r.fingerprint} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 12px", border: `1px solid ${c.line}`, borderRadius: 10, marginBottom: 8, background: c.card }}>
              <Repeat size={14} style={{ color: c.warn, flexShrink: 0 }} />
              <span style={{ flex: 1, minWidth: 0, color: c.ink, fontSize: 12.5, fontFamily: "var(--font-stack-mono)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.url.replace(/^https?:\/\//, "")}</span>
              <span style={{ color: c.warn, fontSize: 12, fontWeight: 700 }}>broke {r.count}×</span>
            </div>
          ))}
        </div>
      )}

      {/* ── ALLOCATION SUGGESTION (suggest, never auto-apply) ── */}
      {f.suggestion && (
        <div style={{ marginTop: 16, border: `1px solid ${c.brand}`, borderRadius: 12, padding: "12px 16px", background: c.raised }}>
          <div style={{ color: c.ink, fontSize: 13.5, fontWeight: 600 }}>{f.suggestion.text}</div>
          <div style={{ color: c.sub, fontSize: 12.5, marginTop: 3 }}>{f.suggestion.evidence}</div>
        </div>
      )}

      {/* ── Client visibility toggle (default OFF — a sales instrument) ── */}
      <div style={{ marginTop: 16, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, paddingTop: 14, borderTop: `1px solid ${c.line}` }}>
        <div style={{ color: c.sub, fontSize: 12.5 }}>{f.client_visible ? "Clients see the positive stability trend on this site." : "Hidden from the client (the raw fragility label is for you)."}</div>
        <button onClick={toggle} disabled={saving} style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "transparent", color: f.client_visible ? c.good : c.sub, border: `1px solid ${c.line}`, borderRadius: 9, padding: "7px 12px", fontSize: 12.5, fontWeight: 600, cursor: "pointer" }}>
          {f.client_visible ? <Eye size={14} /> : <EyeOff size={14} />} {f.client_visible ? "Visible to client" : "Show to client"}
        </button>
      </div>
    </div>
  );
}
