"use client";

import { useCallback, useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, ReferenceArea, Tooltip } from "recharts";
import { Gauge, TrendingUp, TrendingDown, Minus, ChevronDown } from "lucide-react";
import { staffToken, getPortalToken } from "@/lib/backendClient";

type Variant = "dark" | "light";

interface Reg {
  start_at: string; end_at: string; recovered_at: string | null; baseline_p50: number;
  peak_p50: number; delta_ms: number; delta_pct: number; ongoing: boolean;
  window?: { suspects: Array<{ detail: string }>; language: { confidence: string; text: string } };
}
interface Ledger {
  verdict: { state: string; text: string; collecting?: boolean; have?: number; need?: number };
  regressions: Reg[];
  series: Array<{ scanned_at: string; p50: number | null; p90: number | null }>;
}

const T = {
  dark: { ink: "var(--text-primary)", sub: "var(--text-secondary)", muted: "var(--text-muted)", card: "var(--surface-card)", raised: "var(--surface-raised)", line: "var(--border-subtle)", brand: "var(--signal)", good: "var(--status-healthy)", bad: "var(--status-broken)", badbg: "rgba(224,92,92,0.14)", grid: "var(--border-subtle)" },
  light: { ink: "#1c1a2e", sub: "#55506b", muted: "#928da6", card: "#ffffff", raised: "#f4f3f9", line: "#e7e4f0", brand: "var(--signal)", good: "#16a34a", bad: "#dc2626", badbg: "#fef2f2", grid: "#eee9f5" },
};
const dstr = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export default function PerformanceLedger({ variant, siteId, portal, canManage }: { variant: Variant; siteId: string; portal?: boolean; canManage?: boolean }) {
  const c = T[variant];
  const [d, setD] = useState<Ledger | null>(null);
  const [open, setOpen] = useState<string>("");

  const load = useCallback(async () => {
    try {
      const token = portal ? getPortalToken() : await staffToken();
      const res = await fetch(`/api/sites/${siteId}/performance`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      setD(await res.json());
    } catch { setD(null); }
  }, [siteId, portal]);
  useEffect(() => { load(); }, [load]);

  const heading = (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
      <Gauge size={18} style={{ color: c.brand }} />
      <span style={{ fontFamily: "var(--font-stack-display)", fontWeight: 700, fontSize: 18, color: c.ink }}>Load-time ledger</span>
    </div>
  );

  if (d === null) return <div>{heading}<div className="animate-pulse" style={{ height: 220, borderRadius: 14, background: c.raised, border: `1px solid ${c.line}` }} /></div>;

  const v = d.verdict;
  // Collecting-baseline (thin history) — a designed progress state, not an apology.
  if (v.collecting) {
    const pct = Math.round(((v.have || 0) / (v.need || 1)) * 100);
    return <div>{heading}<div style={{ border: `1px solid ${c.line}`, borderRadius: 16, padding: "34px 26px", background: c.raised, textAlign: "center" }}>
      <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 20, fontWeight: 700, color: c.ink }}>Collecting baseline</div>
      <div style={{ color: c.sub, fontSize: 14, marginTop: 6 }}>{v.have}/{v.need} scans — the speed trend appears once there's enough history to be honest.</div>
      <div style={{ height: 8, borderRadius: 999, background: c.line, marginTop: 16, maxWidth: 320, marginInline: "auto", overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: c.brand, transition: "width 300ms" }} />
      </div>
    </div></div>;
  }

  const slower = v.state === "slower";
  const Icon = slower ? TrendingUp : v.state === "faster" ? TrendingDown : Minus;
  const vColor = slower ? c.bad : v.state === "faster" ? c.good : c.sub;
  const data = d.series.filter((p) => p.p50 != null).map((p) => ({ x: dstr(p.scanned_at), raw: p.scanned_at, p50: p.p50 }));

  return (
    <div>{heading}
      {/* ── VERDICT (depth 1) ── */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 16 }}>
        <Icon size={26} style={{ color: vColor, flexShrink: 0, marginTop: 2 }} />
        <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 23, fontWeight: 800, lineHeight: 1.25, color: c.ink, textWrap: "balance" as "balance" }}>{v.text}</div>
      </div>

      {/* ── TREND with regression windows shaded + annotated ON the chart (depth 2) ── */}
      <div style={{ height: 240, border: `1px solid ${c.line}`, borderRadius: 14, padding: "16px 14px 8px", background: c.card }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 20, right: 12, left: 0, bottom: 0 }}>
            <XAxis dataKey="x" tick={{ fill: c.muted, fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={28} />
            <YAxis tick={{ fill: c.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={44}
              tickFormatter={(n) => `${(n / 1000).toFixed(1)}s`} />
            <Tooltip contentStyle={{ background: c.card, border: `1px solid ${c.line}`, borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: c.sub }} formatter={(val) => [`${val}ms`, "typical load (p50)"]} />
            {d.regressions.map((r, i) => (
              <ReferenceArea key={i} x1={dstr(r.start_at)} x2={dstr(r.recovered_at || r.end_at)}
                fill={c.bad} fillOpacity={0.14} stroke={c.bad} strokeOpacity={0.3}
                label={{ value: r.window?.language?.text?.slice(0, 40) || "regression", position: "insideTop",
                         fill: c.bad, fontSize: 10, fontWeight: 600 }} />
            ))}
            <Line type="monotone" dataKey="p50" stroke={c.brand} strokeWidth={2.5} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div style={{ color: c.muted, fontSize: 11.5, marginTop: 6 }}>Line = typical load (p50 — half of loads were faster). Shaded = a sustained slowdown; the label names what changed in that window.</div>

      {/* ── Regression evidence rows (depth 3) ── */}
      {d.regressions.length > 0 && (
        <div style={{ marginTop: 14, border: `1px solid ${c.line}`, borderRadius: 12, overflow: "hidden" }}>
          {d.regressions.map((r, i) => {
            const isOpen = open === `${i}`;
            return (
              <div key={i} style={{ borderTop: i ? `1px solid ${c.line}` : "none", background: c.badbg }}>
                <div onClick={() => setOpen(isOpen ? "" : `${i}`)} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 14px", cursor: "pointer" }}>
                  <TrendingUp size={15} style={{ color: c.bad, flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: c.ink, fontSize: 13.5, fontWeight: 600 }}>+{r.delta_ms}ms slower from {dstr(r.start_at)}{r.ongoing ? " (ongoing)" : ` to ${dstr(r.recovered_at || r.end_at)}`}</div>
                    <div style={{ color: c.sub, fontSize: 12.5, marginTop: 2 }}>{r.window?.language?.text || "no recorded change in this window"}</div>
                  </div>
                  <span style={{ fontFamily: "var(--font-stack-mono)", fontSize: 12.5, color: c.bad }}>+{r.delta_pct}%</span>
                  <ChevronDown size={14} style={{ color: c.muted, transform: isOpen ? "rotate(180deg)" : "none", transition: "transform 150ms" }} />
                </div>
                {isOpen && (
                  <div style={{ padding: "2px 14px 14px 41px", fontSize: 12.5, color: c.sub }}>
                    <div>Baseline {r.baseline_p50}ms → peak {r.peak_p50}ms.</div>
                    {(r.window?.suspects || []).length > 0 ? (
                      <ul style={{ margin: "6px 0 0", paddingLeft: 16 }}>
                        {r.window!.suspects.map((s, j) => <li key={j} style={{ color: c.ink }}>{s.detail}</li>)}
                      </ul>
                    ) : <div style={{ color: c.muted, marginTop: 4 }}>Nothing recorded changed on the site in this window — the cause is elsewhere (host, network, or an unmonitored change).</div>}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {canManage && !portal && <CostIndex c={c} />}
    </div>
  );
}

function CostIndex({ c }: { c: typeof T.dark }) {
  const [idx, setIdx] = useState<{ index: Array<{ host: string; sites: number; median_added_ms: number }>; method: string } | null>(null);
  useEffect(() => { (async () => {
    try { const t = await staffToken(); const r = await fetch("/api/performance/cost-index", { headers: t ? { Authorization: `Bearer ${t}` } : {} }); setIdx(await r.json()); } catch { setIdx({ index: [], method: "" }); }
  })(); }, []);
  if (!idx || !idx.index || idx.index.length === 0) return null;
  return (
    <div style={{ marginTop: 20 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: c.ink, marginBottom: 4 }}>Third-party cost across your portfolio</div>
      <div style={{ color: c.muted, fontSize: 11.5, marginBottom: 10 }}>{idx.method}</div>
      <div style={{ border: `1px solid ${c.line}`, borderRadius: 12, overflow: "hidden" }}>
        {idx.index.slice(0, 8).map((h, i) => (
          <div key={h.host} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", borderTop: i ? `1px solid ${c.line}` : "none", background: c.card }}>
            <span style={{ flex: 1, color: c.ink, fontSize: 13, fontFamily: "var(--font-stack-mono)" }}>{h.host}</span>
            <span style={{ color: c.muted, fontSize: 12 }}>on {h.sites} site{h.sites === 1 ? "" : "s"}</span>
            <span style={{ fontFamily: "var(--font-stack-mono)", fontSize: 13.5, fontWeight: 700, color: c.bad }}>+{h.median_added_ms}ms</span>
          </div>
        ))}
      </div>
    </div>
  );
}
