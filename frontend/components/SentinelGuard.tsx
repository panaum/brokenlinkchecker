"use client";

import { useCallback, useEffect, useState } from "react";
import { ShieldCheck, ShieldAlert, Lock, Globe, Search, Activity, RefreshCw, Loader2, Check, X, HelpCircle, ChevronDown } from "lucide-react";
import { staffToken, getPortalToken } from "@/lib/backendClient";

type Variant = "dark" | "light";

interface Sub { key: string; label: string; status: string; text: string; }
interface Card { key: string; label: string; days: number | null; escalation: string; fact: string; detail?: string | null; checks?: Sub[]; }
interface Incident { id: string; down_at: string; restored_at: string | null; }
interface Sentinel {
  cards: Card[]; worst: string; all_clear: boolean; last_checked: string | null;
  uptime_pct: number | null; down: boolean; incidents: Incident[];
}

const T = {
  dark: { ink: "var(--text-primary)", sub: "var(--text-secondary)", muted: "var(--text-muted)",
    card: "var(--surface-card)", raised: "var(--surface-raised)", line: "var(--border-subtle)",
    brand: "var(--signal)", good: "var(--status-healthy)", notice: "var(--status-attention)", warn: "#f5a623", crit: "var(--status-broken)", critbg: "rgba(224,92,92,0.12)", noticebg: "rgba(245,166,35,0.10)" },
  light: { ink: "#1c1a2e", sub: "#55506b", muted: "#928da6",
    card: "#ffffff", raised: "#f4f3f9", line: "#e7e4f0",
    brand: "var(--signal)", good: "#16a34a", notice: "#d97706", warn: "#ea580c", crit: "#dc2626", critbg: "#fef2f2", noticebg: "#fffbeb" },
};

const ICON = { ssl: Lock, domain: Globe, index: Search, uptime: Activity } as const;

function escColor(esc: string, c: typeof T.dark): string {
  return esc === "critical" ? c.crit : esc === "warn" ? c.warn : esc === "notice" ? c.notice
    : esc === "unknown" ? c.muted : c.good;
}
function ago(iso: string | null): string {
  if (!iso) return "never";
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 90) return "just now"; if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`; return `${Math.floor(s / 86400)}d ago`;
}
function fmtDate(iso: string): string { return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }
function duration(a: string, b: string | null): string {
  const end = b ? new Date(b).getTime() : Date.now();
  const m = Math.max(1, Math.round((end - new Date(a).getTime()) / 60000));
  return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

export default function SentinelGuard({ variant, siteId, portal, canManage }:
  { variant: Variant; siteId?: string; portal?: boolean; canManage?: boolean }) {
  const c = T[variant];
  const [data, setData] = useState<Sentinel | null>(null);
  const [busy, setBusy] = useState(false);
  const [openKey, setOpenKey] = useState<string>("");
  const [showLog, setShowLog] = useState(false);

  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const token = portal ? getPortalToken() : await staffToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [portal]);

  const load = useCallback(async () => {
    if (!siteId) return;
    try {
      const res = await fetch(`/api/sites/${siteId}/sentinel`, { headers: await authHeaders() });
      setData(await res.json());
    } catch { setData(null); }
  }, [siteId, authHeaders]);

  useEffect(() => { load(); }, [load]);

  const checkNow = async () => {
    setBusy(true);
    try {
      const res = await fetch(`/api/sites/${siteId}/sentinel/check-now`, { method: "POST", headers: await authHeaders() });
      if (res.ok) setData(await res.json());
    } finally { setBusy(false); }
  };

  const header = (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {data && !data.all_clear ? <ShieldAlert size={18} style={{ color: c.crit }} /> : <ShieldCheck size={18} style={{ color: c.brand }} />}
        <span style={{ fontFamily: "var(--font-stack-display)", fontWeight: 700, fontSize: 18, color: c.ink }}>Disaster sentinel</span>
      </div>
      {canManage && siteId && (
        <button onClick={checkNow} disabled={busy} style={{ display: "inline-flex", alignItems: "center", gap: 7, background: "transparent", color: c.sub, border: `1px solid ${c.line}`, borderRadius: 9, padding: "8px 14px", fontSize: 13, fontWeight: 600, cursor: busy ? "wait" : "pointer" }}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} Check now
        </button>
      )}
    </div>
  );

  if (data === null) {
    return <div>{header}<div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px,1fr))", gap: 12 }}>{[0, 1, 2, 3].map(i => <div key={i} className="animate-pulse" style={{ height: 110, borderRadius: 12, background: c.raised, border: `1px solid ${c.line}` }} />)}</div></div>;
  }
  if (!data.cards || data.cards.length === 0) {
    return <div>{header}<div style={{ border: `1px dashed ${c.line}`, borderRadius: 14, padding: "34px 20px", textAlign: "center", background: c.raised }}>
      <ShieldCheck size={26} style={{ color: c.good, marginBottom: 10 }} />
      <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 16, fontWeight: 600, color: c.ink }}>Sentinel not run yet</div>
      <div style={{ color: c.sub, fontSize: 13.5, marginTop: 5 }}>{canManage ? "Run the first check to watch SSL, domain, search visibility and uptime." : "SSL, domain, search visibility and uptime will be watched here."}</div>
    </div></div>;
  }

  return (
    <div>{header}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(155px, 1fr))", gap: 12 }}>
        {data.cards.map((card) => {
          const col = escColor(card.escalation, c);
          const crit = card.escalation === "critical";
          const notice = card.escalation === "notice" || card.escalation === "warn";
          const Icon = ICON[card.key as keyof typeof ICON] || ShieldCheck;
          const expandable = card.key === "index" || card.key === "uptime";
          const open = openKey === card.key;
          return (
            <div key={card.key}
              onClick={() => expandable && setOpenKey(open ? "" : card.key)}
              style={{
                gridColumn: crit ? "1 / -1" : "auto",  // critical cards span full width, first
                borderRadius: 12, padding: crit ? "18px 20px" : "14px 16px",
                background: crit ? c.critbg : notice ? c.noticebg : c.card,
                border: `1px solid ${crit ? c.crit : notice ? col : c.line}`,
                cursor: expandable ? "pointer" : "default",
              }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                  <Icon size={15} style={{ color: card.escalation === "ok" ? c.muted : col }} />
                  <span style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: c.sub }}>{card.label}</span>
                </div>
                {card.escalation === "ok" && <Check size={14} style={{ color: c.good }} />}
                {expandable && <ChevronDown size={13} style={{ color: c.muted, transform: open ? "rotate(180deg)" : "none", transition: "transform 150ms" }} />}
              </div>
              {/* The fact — day number becomes the biggest element when critical */}
              <div style={{ marginTop: crit ? 10 : 8, display: "flex", alignItems: "baseline", gap: 6 }}>
                {card.days != null ? (
                  <>
                    <span style={{ fontFamily: "var(--font-stack-mono)", fontWeight: 800, lineHeight: 1, color: col, fontSize: crit ? 46 : notice ? 30 : 22 }}>{card.days}</span>
                    <span style={{ fontSize: 12, color: c.sub }}>day{card.days === 1 ? "" : "s"} left</span>
                  </>
                ) : (
                  <span style={{ fontFamily: "var(--font-stack-mono)", fontWeight: 700, fontSize: crit ? 30 : 20, color: col }}>{card.fact}</span>
                )}
              </div>
              {card.detail && <div style={{ color: c.muted, fontSize: 11.5, marginTop: 4 }}>{card.detail}</div>}
              {crit && <div style={{ color: c.crit, fontSize: 12.5, fontWeight: 600, marginTop: 6 }}>Needs attention now</div>}

              {/* Indexability sub-checks */}
              {card.key === "index" && open && card.checks && (
                <div onClick={(e) => e.stopPropagation()} style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                  {card.checks.map((s) => (
                    <div key={s.key} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12.5, color: c.sub }}>
                      {s.status === "ok" ? <Check size={14} style={{ color: c.good, flexShrink: 0, marginTop: 1 }} />
                        : s.status === "unknown" ? <HelpCircle size={14} style={{ color: c.muted, flexShrink: 0, marginTop: 1 }} />
                        : <X size={14} style={{ color: c.crit, flexShrink: 0, marginTop: 1 }} />}
                      <span>{s.text}</span>
                    </div>
                  ))}
                </div>
              )}
              {/* Uptime incident log */}
              {card.key === "uptime" && open && (
                <div onClick={(e) => e.stopPropagation()} style={{ marginTop: 12 }}>
                  {(!data.incidents || data.incidents.length === 0) ? (
                    <div style={{ color: c.good, fontSize: 12.5, display: "flex", alignItems: "center", gap: 6 }}><Check size={13} /> No downtime recorded</div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {data.incidents.slice(0, 6).map((inc) => (
                        <div key={inc.id} style={{ fontSize: 12, color: c.sub, fontFamily: "var(--font-stack-mono)" }}>
                          <span style={{ color: c.crit }}>↓ {fmtDate(inc.down_at)}</span>
                          {inc.restored_at ? <span style={{ color: c.good }}> · ↑ {fmtDate(inc.restored_at)} · {duration(inc.down_at, inc.restored_at)}</span>
                                           : <span style={{ color: c.crit }}> · still down · {duration(inc.down_at, null)}</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {data.last_checked && <div style={{ color: c.muted, fontSize: 12, marginTop: 10 }}>Last checked {ago(data.last_checked)}</div>}
    </div>
  );
}
