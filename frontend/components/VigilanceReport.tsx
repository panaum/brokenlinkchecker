"use client";

import React, { useEffect, useRef, useState } from "react";
import { LineChart, Line, YAxis, ResponsiveContainer } from "recharts";
import { Check, ShieldCheck } from "lucide-react";

// ── Boardroom-light palette (self-contained; not the app's dark theme) ──
const INK = "#1c1a2e";
const SECONDARY = "#55506b";
const MUTED = "#928da6";
const PAPER = "#ffffff";
const PAGE = "#f4f3f9";
const LINE = "#e7e4f0";
const BRAND = "#7c3aed";
const GREEN = "#16a34a";
const RED = "#dc2626";
const AMBER = "#d97706";

export interface ReportData {
  period: { start: string; end: string; label: string };
  all_clear: boolean;
  verdict: string;
  score: number | null;
  score_delta: number;
  streak_days: number;
  vigilance: { checks_run: number; links_verified: number; forms_audited: number; integrations_watched: number };
  caught_count: number;
  fixed_count: number;
  incidents: Array<{
    found_at: string | null; fixed_at: string | null; verified: boolean;
    bucket: string; what: string; where: string; url: string; hours_to_fix?: number; roi_line?: string;
  }>;
  trend: Array<{ date: string; score: number }>;
  uptime_pct: number | null;
  ads?: { destinations_verified: number; incidents: number; has_cost: boolean; spend_at_risk: number | null } | null;
}

function useCountUp(target: number, ms = 600): number {
  const [v, setV] = useState(0);
  const ref = useRef(0);
  useEffect(() => {
    const reduce = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { setV(target); return; }
    const from = ref.current; const start = performance.now(); let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      const cur = Math.round(from + (target - from) * (1 - Math.pow(1 - t, 4)));
      setV(cur); ref.current = cur;
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
function scoreColor(s: number | null): string {
  if (s == null) return MUTED;
  if (s >= 90) return GREEN;
  if (s >= 70) return AMBER;
  return RED;
}

function Stat({ value, label }: { value: number; label: string }) {
  const shown = useCountUp(value);
  return (
    <div style={{ textAlign: "center", flex: 1, minWidth: 120 }}>
      <div style={{ fontFamily: "var(--font-stack-mono)", fontSize: 44, fontWeight: 700, color: INK, fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>{shown}</div>
      <div style={{ color: SECONDARY, fontSize: 13, marginTop: 8, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</div>
    </div>
  );
}

export default function VigilanceReport({ data, siteName }: { data: ReportData; siteName: string }) {
  const shownScore = useCountUp(data.score ?? 0);
  const R = 52; const C = 2 * Math.PI * R;
  const ring = scoreColor(data.score);

  return (
    <div className="report-root" style={{ background: PAGE, minHeight: "100vh", padding: "40px 20px", color: INK, fontFamily: "var(--font-stack-body)" }}>
      <article style={{ maxWidth: 860, margin: "0 auto", background: PAPER, borderRadius: 20, boxShadow: "0 10px 40px rgba(28,26,46,0.10)", overflow: "hidden" }}>

        {/* ── Masthead ── */}
        <header className="report-masthead" style={{ padding: "40px 48px 28px", borderBottom: `1px solid ${LINE}` }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
            <div>
              <div style={{ fontFamily: "var(--font-stack-display)", fontWeight: 800, fontSize: 20, letterSpacing: "-0.02em" }}>
                Link<span style={{ color: BRAND }}>Spy</span> <span style={{ color: MUTED, fontWeight: 500, fontSize: 14 }}>· by Apexure</span>
              </div>
              <div style={{ color: SECONDARY, fontSize: 14, marginTop: 6 }}>Prepared for <strong style={{ color: INK }}>{siteName}</strong></div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 38, fontWeight: 800, lineHeight: 1, letterSpacing: "-0.02em" }}>{data.period.label}</div>
              <div style={{ color: MUTED, fontSize: 12, marginTop: 4, textTransform: "uppercase", letterSpacing: "0.08em" }}>Vigilance report</div>
            </div>
          </div>
        </header>

        {/* ── Verdict hero ── */}
        <section className="report-block" style={{ padding: "40px 48px", display: "flex", alignItems: "center", gap: 36, flexWrap: "wrap", borderBottom: `1px solid ${LINE}` }}>
          <div style={{ position: "relative", width: 128, height: 128, flexShrink: 0 }}>
            <svg width="128" height="128" viewBox="0 0 128 128">
              <circle cx="64" cy="64" r={R} fill="none" stroke={LINE} strokeWidth="9" />
              <circle cx="64" cy="64" r={R} fill="none" stroke={ring} strokeWidth="9" strokeLinecap="round"
                strokeDasharray={C} strokeDashoffset={C * (1 - (data.score ?? 0) / 100)} transform="rotate(-90 64 64)" />
            </svg>
            <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
              <span style={{ fontFamily: "var(--font-stack-mono)", fontSize: 34, fontWeight: 700, color: ring, lineHeight: 1 }}>{shownScore}</span>
              <span style={{ fontFamily: "var(--font-stack-mono)", fontSize: 11, color: MUTED }}>/ 100</span>
            </div>
          </div>
          <div style={{ flex: 1, minWidth: 260 }}>
            <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 30, fontWeight: 700, lineHeight: 1.2, letterSpacing: "-0.01em" }}>{data.verdict}</div>
            {data.score_delta !== 0 && (
              <div style={{ marginTop: 10, fontFamily: "var(--font-stack-mono)", fontSize: 14, color: data.score_delta > 0 ? GREEN : RED }}>
                {data.score_delta > 0 ? "▲ +" : "▼ "}{data.score_delta} vs start of period
              </div>
            )}
          </div>
        </section>

        {/* ── Vigilance strip (the hero when nothing broke) ── */}
        <section className="report-block" style={{ padding: "36px 48px", background: data.all_clear ? "#f8f6ff" : PAPER, borderBottom: `1px solid ${LINE}` }}>
          {data.all_clear && (
            <div style={{ display: "flex", alignItems: "center", gap: 10, justifyContent: "center", marginBottom: 24, color: GREEN }}>
              <ShieldCheck size={18} /> <span style={{ fontWeight: 600, fontSize: 15 }}>Nothing broke on your watch this period.</span>
            </div>
          )}
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", justifyContent: "space-between" }}>
            <Stat value={data.vigilance.checks_run} label="Checks run" />
            <Stat value={data.vigilance.links_verified} label="Links verified" />
            <Stat value={data.vigilance.forms_audited} label="Forms audited" />
            <Stat value={data.vigilance.integrations_watched} label="Integrations watched" />
          </div>
          {/* Ad spend protected — only when Ads destinations were imported (honest) */}
          {data.ads && data.ads.destinations_verified > 0 && (
            <div style={{ marginTop: 24, paddingTop: 20, borderTop: `1px solid ${LINE}`, textAlign: "center", color: SECONDARY, fontSize: 14 }}>
              <b style={{ color: INK }}>{data.ads.destinations_verified}</b> ad destination{data.ads.destinations_verified === 1 ? "" : "s"} verified daily
              {data.ads.incidents > 0
                ? <> · <b style={{ color: RED }}>{data.ads.incidents}</b> live ad{data.ads.incidents === 1 ? "" : "s"} caught pointing at a dead page</>
                : <> · none pointing at a dead page</>}
              {data.ads.has_cost && data.ads.spend_at_risk != null && data.ads.spend_at_risk > 0 && (
                <> · ≈ ${data.ads.spend_at_risk.toLocaleString()}/day protected</>
              )}
            </div>
          )}
        </section>

        {/* ── Caught & fixed timeline ── */}
        {data.incidents.length > 0 && (
          <section className="report-block" style={{ padding: "36px 48px", borderBottom: `1px solid ${LINE}` }}>
            <h2 style={{ fontFamily: "var(--font-stack-display)", fontSize: 20, fontWeight: 700, marginBottom: 24 }}>What we caught &amp; fixed</h2>
            <div style={{ position: "relative", paddingLeft: 24 }}>
              <div style={{ position: "absolute", left: 5, top: 6, bottom: 6, width: 2, background: LINE }} />
              {data.incidents.map((inc, i) => (
                <div key={i} className="report-incident" style={{ position: "relative", marginBottom: i === data.incidents.length - 1 ? 0 : 20 }}>
                  <div style={{ position: "absolute", left: -24, top: 4, width: 12, height: 12, borderRadius: "50%", background: inc.verified ? GREEN : AMBER, border: `2px solid ${PAPER}`, boxShadow: `0 0 0 2px ${inc.verified ? GREEN : AMBER}` }} />
                  <div style={{ background: PAGE, border: `1px solid ${LINE}`, borderRadius: 12, padding: "16px 18px" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                      <div style={{ fontWeight: 600, fontSize: 15, color: INK }}>{inc.what}</div>
                      {inc.verified && (
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 5, background: "#dcfce7", color: GREEN, fontSize: 12, fontWeight: 600, padding: "3px 9px", borderRadius: 999 }}>
                          <Check size={12} /> Verified fixed
                        </span>
                      )}
                    </div>
                    {inc.where && <div style={{ color: SECONDARY, fontSize: 13, marginTop: 3 }}>{inc.where}</div>}
                    <div style={{ display: "flex", gap: 18, marginTop: 10, fontFamily: "var(--font-stack-mono)", fontSize: 12, color: MUTED, flexWrap: "wrap" }}>
                      {inc.found_at && <span>Found {fmtDate(inc.found_at)}</span>}
                      {inc.fixed_at && <span style={{ color: GREEN }}>→ Fixed {fmtDate(inc.fixed_at)}</span>}
                      {inc.hours_to_fix != null && <span>({inc.hours_to_fix}h)</span>}
                    </div>
                    {inc.roi_line && <div style={{ marginTop: 8, color: BRAND, fontSize: 13, fontWeight: 600 }}>{inc.roi_line}</div>}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ── Trend ── */}
        {data.trend.length >= 2 && (
          <section className="report-block" style={{ padding: "36px 48px", borderBottom: `1px solid ${LINE}` }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
              <h2 style={{ fontFamily: "var(--font-stack-display)", fontSize: 20, fontWeight: 700 }}>Health this period</h2>
              <div style={{ fontFamily: "var(--font-stack-mono)", fontSize: 14, color: GREEN }}>{data.streak_days} days clean</div>
            </div>
            <div style={{ height: 120 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.trend}>
                  <YAxis domain={[0, 100]} width={28} tick={{ fill: MUTED, fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Line type="monotone" dataKey="score" stroke={BRAND} strokeWidth={2.5} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>
        )}

        {/* ── Footer ── */}
        <footer style={{ padding: "28px 48px", color: SECONDARY, fontSize: 13, display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div>Next period we keep watching your links, forms, CTAs, tracking &amp; integrations — continuously.</div>
          <div style={{ textAlign: "right", color: MUTED }}>Apexure · success@apexure.com</div>
        </footer>
      </article>
    </div>
  );
}
