"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Target, Check, X, HelpCircle, ChevronDown, ExternalLink } from "lucide-react";
import { staffToken, getPortalToken } from "@/lib/backendClient";

type Variant = "dark" | "light";

interface Promise {
  type: string; tier: number; label: string; anchor: string; zone: string; zone_class: string;
  url: string; final_url: string; verdict: string; evidence: string; severity: string | null; weight: number;
}
interface Map {
  verdict: string; all_clear: boolean; no_scan?: boolean;
  counts: { conversion_total: number; honored: number; broken: number; unverified: number; functional_total: number };
  promises: Promise[];
}

const T = {
  dark: { ink: "var(--text-primary)", sub: "var(--text-secondary)", muted: "var(--text-muted)", card: "var(--surface-card)", raised: "var(--surface-raised)", line: "rgba(255,255,255,0.08)", brand: "#a855f7", good: "#4ade80", bad: "#f87171", badbg: "rgba(248,113,113,0.12)", gray: "#8b93a7" },
  light: { ink: "#1c1a2e", sub: "#55506b", muted: "#928da6", card: "#ffffff", raised: "#f4f3f9", line: "#e7e4f0", brand: "#7c3aed", good: "#16a34a", bad: "#dc2626", badbg: "#fef2f2", gray: "#8a86a0" },
};

// Plain-language definitions, attached at point of contact (title=).
const VERDICT_DEF: Record<string, string> = {
  honored: "Honored — the promise's destination does what the link says.",
  broken: "Broken — the destination can't deliver what the link promises.",
  unverified: "Unverified — we couldn't confirm from here (bot-blocked or gated); not counted as broken.",
};

function useCountUp(target: number, ms = 650) {
  const [v, setV] = useState(0); const ref = useRef(0);
  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setV(target); return; }
    const from = ref.current, start = performance.now(); let raf = 0;
    const tick = (n: number) => { const t = Math.min(1, (n - start) / ms); const cur = Math.round(from + (target - from) * (1 - Math.pow(1 - t, 4))); setV(cur); ref.current = cur; if (t < 1) raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick); return () => cancelAnimationFrame(raf);
  }, [target, ms]); return v;
}
function midTrunc(url: string, head = 30, tail = 16): string {
  const u = (url || "").replace(/^https?:\/\//, "");
  return u.length <= head + tail + 1 ? u : u.slice(0, head) + "…" + u.slice(-tail);
}

export default function IntentMap({ variant, siteId, portal, canEnroll }: { variant: Variant; siteId: string; portal?: boolean; canEnroll?: boolean }) {
  const c = T[variant];
  const soft = !!portal;   // portal register softens copy
  const [map, setMap] = useState<Map | null>(null);
  const [open, setOpen] = useState<string>("");

  const load = useCallback(async () => {
    try {
      const token = portal ? getPortalToken() : await staffToken();
      const res = await fetch(`/api/sites/${siteId}/intent-map`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      setMap(await res.json());
    } catch { setMap(null); }
  }, [siteId, portal]);
  useEffect(() => { load(); }, [load]);

  const honored = useCountUp(map?.counts.honored ?? 0);
  const total = useCountUp(map?.counts.conversion_total ?? 0);

  const heading = (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
      <Target size={18} style={{ color: c.brand }} />
      <span style={{ fontFamily: "var(--font-stack-display)", fontWeight: 700, fontSize: 18, color: c.ink }}>Promise map</span>
    </div>
  );

  if (map === null) return <div>{heading}<div className="animate-pulse" style={{ height: 120, borderRadius: 14, background: c.raised, border: `1px solid ${c.line}` }} /></div>;

  if (map.no_scan || map.counts.conversion_total === 0) {
    return <div>{heading}<div style={{ border: `1px dashed ${c.line}`, borderRadius: 16, padding: "38px 24px", textAlign: "center", background: c.raised }}>
      <Target size={26} style={{ color: c.muted, marginBottom: 10 }} />
      <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 16, fontWeight: 600, color: c.ink }}>{map.no_scan ? "No scan yet" : "No conversion promises detected"}</div>
      <div style={{ color: c.sub, fontSize: 13.5, marginTop: 5 }}>{map.no_scan ? "Run a scan to map this site's promises." : "This site's links don't make machine-verifiable conversion promises (book, contact, download, pricing, signup)."}</div>
    </div></div>;
  }

  const broken = map.counts.broken;

  return (
    <div>{heading}
      {/* ── VERDICT HERO (depth 1) ── */}
      <div style={{ borderRadius: 16, padding: "26px 26px", border: `1px solid ${broken ? c.bad : c.line}`, background: broken ? c.badbg : c.raised }}>
        <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 24, fontWeight: 800, lineHeight: 1.2, color: broken ? c.ink : c.ink, textWrap: "balance" as "balance" }}>
          {map.all_clear
            ? (soft ? `Every conversion promise on your site is honored.` : map.verdict)
            : map.verdict}
        </div>
        {/* depth-2 count strip — each number defined on hover */}
        <div style={{ display: "flex", gap: 22, marginTop: 16, flexWrap: "wrap" }}>
          <Stat n={total} label="promises" color={c.ink} c={c} title="Conversion promises detected on this site (book, contact, download, pricing, signup)." />
          <Stat n={honored} label="honored" color={c.good} c={c} title={VERDICT_DEF.honored} />
          {broken > 0 && <Stat n={broken} label="broken" color={c.bad} c={c} title={VERDICT_DEF.broken} />}
          {map.counts.unverified > 0 && <Stat n={map.counts.unverified} label="unverified" color={c.gray} c={c} title={VERDICT_DEF.unverified} />}
        </div>
      </div>

      {/* ── EVIDENCE ROWS (depth 2 + expandable depth 3) — broken first ── */}
      <div style={{ marginTop: 16, border: `1px solid ${c.line}`, borderRadius: 12, overflow: "hidden" }}>
        {map.promises.map((p, i) => {
          const col = p.verdict === "honored" ? c.good : p.verdict === "broken" ? c.bad : c.gray;
          const Icon = p.verdict === "honored" ? Check : p.verdict === "broken" ? X : HelpCircle;
          const isOpen = open === `${i}`;
          return (
            <div key={i} style={{ borderTop: i ? `1px solid ${c.line}` : "none", background: p.verdict === "broken" ? c.badbg : c.card }}>
              <div onClick={() => setOpen(isOpen ? "" : `${i}`)} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 14px", cursor: "pointer" }}>
                <Icon size={16} style={{ color: col, flexShrink: 0 }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ color: c.ink, fontSize: 13.5, fontWeight: 600 }}>&ldquo;{p.anchor}&rdquo;</span>
                    <span style={{ fontSize: 10.5, color: c.muted, textTransform: "uppercase", letterSpacing: "0.05em", border: `1px solid ${c.line}`, padding: "1px 6px", borderRadius: 999 }}>{p.zone_class}</span>
                    <span style={{ fontSize: 10.5, color: c.muted, border: `1px solid ${c.line}`, padding: "1px 6px", borderRadius: 999 }}>{p.label}</span>
                  </div>
                  <div style={{ color: c.sub, fontSize: 12.5, marginTop: 3 }} title={VERDICT_DEF[p.verdict]}>{p.evidence}</div>
                </div>
                <span style={{ color: col, fontSize: 12, fontWeight: 700, textTransform: "capitalize", flexShrink: 0 }} title={VERDICT_DEF[p.verdict]}>{p.verdict}</span>
                <ChevronDown size={14} style={{ color: c.muted, transform: isOpen ? "rotate(180deg)" : "none", transition: "transform 150ms", flexShrink: 0 }} />
              </div>
              {isOpen && (
                <div style={{ padding: "2px 14px 14px 42px", fontSize: 12.5, color: c.sub, display: "flex", flexDirection: "column", gap: 5 }}>
                  <a href={p.final_url || p.url} target="_blank" rel="noreferrer" style={{ color: c.sub, fontFamily: "var(--font-stack-mono)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 5 }} title={p.final_url || p.url}>
                    {midTrunc(p.final_url || p.url)} <ExternalLink size={11} />
                  </a>
                  {p.severity && <div>Severity if unaddressed: <b style={{ color: p.severity === "critical" ? c.bad : c.ink }}>{p.severity}</b> ({p.zone_class} placement).</div>}
                  <div style={{ color: c.muted }}>Promise type <b style={{ color: c.ink }}>{p.type}</b> · tier {p.tier} · verified by joining the destination's links, forms and integrations.</div>
                </div>
              )}
            </div>
          );
        })}
      </div>
      {map.counts.functional_total > 0 && <div style={{ color: c.muted, fontSize: 12, marginTop: 8 }}>Plus {map.counts.functional_total} functional promise{map.counts.functional_total === 1 ? "" : "s"} (watch, call, directions, apply, chat) — shown above, weighted below conversion.</div>}
    </div>
  );
}

function Stat({ n, label, color, c, title }: { n: number; label: string; color: string; c: typeof T.dark; title: string }) {
  return (
    <div title={title} style={{ cursor: "help" }}>
      <span style={{ fontFamily: "var(--font-stack-mono)", fontSize: 30, fontWeight: 800, color, fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>{n}</span>
      <span style={{ color: c.sub, fontSize: 12.5, marginLeft: 7 }}>{label}</span>
    </div>
  );
}
