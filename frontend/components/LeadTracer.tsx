"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { BadgeCheck, ShieldAlert, Loader2, ChevronDown, Check, X, Plug, Play } from "lucide-react";
import { staffToken, getPortalToken } from "@/lib/backendClient";

type Variant = "dark" | "light";

interface Arrival { field: string; crm_property: string; arrived: boolean; arrived_value_matches: boolean; }
interface Run { id: string; started_at: string; mode: string; outcome: string; arrival: Arrival[]; cleanup: string; evidence?: Record<string, unknown>; }
interface Stamp { state: string; consecutive_days: number; last_run_at: string | null; last_verified_at: string | null; last_outcome?: string; broken_since: string | null; }
interface Contract { contract_key: string; status: string; form_ref: { page_url: string; form_id: string }; }

const T = {
  dark: { ink: "var(--text-primary)", sub: "var(--text-secondary)", muted: "var(--text-muted)", card: "var(--surface-card)", raised: "var(--surface-raised)", line: "rgba(255,255,255,0.08)", brand: "#a855f7", good: "#4ade80", bad: "#f87171", badbg: "rgba(248,113,113,0.12)" },
  light: { ink: "#1c1a2e", sub: "#55506b", muted: "#928da6", card: "#ffffff", raised: "#f4f3f9", line: "#e7e4f0", brand: "#7c3aed", good: "#16a34a", bad: "#dc2626", badbg: "#fef2f2" },
};

function useCountUp(target: number, ms = 700) {
  const [v, setV] = useState(0); const ref = useRef(0);
  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setV(target); return; }
    const from = ref.current, start = performance.now(); let raf = 0;
    const tick = (n: number) => { const t = Math.min(1, (n - start) / ms); const cur = Math.round(from + (target - from) * (1 - Math.pow(1 - t, 4))); setV(cur); ref.current = cur; if (t < 1) raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick); return () => cancelAnimationFrame(raf);
  }, [target, ms]); return v;
}
const fmt = (iso: string | null) => iso ? new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";

export default function LeadTracer({ variant, siteId, portal, canManage }: { variant: Variant; siteId: string; portal?: boolean; canManage?: boolean }) {
  const c = T[variant];
  const [stamp, setStamp] = useState<Stamp | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [openRun, setOpenRun] = useState<string>("");
  const [setup, setSetup] = useState(false);
  const days = useCountUp(stamp?.consecutive_days ?? 0);

  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    const token = portal ? getPortalToken() : await staffToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [portal]);

  const load = useCallback(async () => {
    try {
      const h = await authHeaders();
      const [s, r] = await Promise.all([
        fetch(`/api/sites/${siteId}/tracer/stamp`, { headers: h }).then((x) => x.json()),
        fetch(`/api/sites/${siteId}/tracer/runs`, { headers: h }).then((x) => x.json()),
      ]);
      setStamp(s); setRuns(r.runs || []);
    } catch { setStamp({ state: "none", consecutive_days: 0, last_run_at: null, last_verified_at: null, broken_since: null }); }
  }, [siteId, authHeaders]);
  useEffect(() => { load(); }, [load]);

  if (stamp === null) return <div className="animate-pulse" style={{ height: 130, borderRadius: 14, background: c.raised, border: `1px solid ${c.line}` }} />;

  const broken = stamp.state === "broken";
  const none = stamp.state === "none";

  return (
    <div>
      {/* ── THE STAMP — the primary surface ── */}
      <div style={{ borderRadius: 16, padding: "22px 24px", border: `1px solid ${broken ? c.bad : c.line}`, background: broken ? c.badbg : c.raised, display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>
        {broken ? <ShieldAlert size={34} style={{ color: c.bad, flexShrink: 0 }} /> : <BadgeCheck size={34} style={{ color: none ? c.muted : c.good, flexShrink: 0 }} />}
        <div style={{ flex: 1, minWidth: 220 }}>
          {none ? (
            <>
              <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 20, fontWeight: 700, color: c.ink }}>Lead delivery — not yet verified</div>
              <div style={{ color: c.sub, fontSize: 13.5, marginTop: 4 }}>{canManage ? "Connect a CRM and enroll a form to start the daily tracer." : "Your agency will begin verifying lead delivery here."}</div>
            </>
          ) : broken ? (
            <>
              <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 22, fontWeight: 800, color: c.bad }}>Lead pipeline needs attention</div>
              <div style={{ color: c.sub, fontSize: 13.5, marginTop: 4 }}>Last check {fmt(stamp.last_run_at)} · {stamp.last_outcome} · since {fmt(stamp.broken_since)}</div>
            </>
          ) : (
            <>
              <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 22, fontWeight: 800, color: c.ink }}>Lead pipeline verified</div>
              <div style={{ color: c.sub, fontSize: 13.5, marginTop: 4 }}>Today {fmt(stamp.last_verified_at)} · submitted, arrived field-by-field, cleaned up</div>
            </>
          )}
        </div>
        {!none && (
          <div style={{ textAlign: "center" }}>
            <div style={{ fontFamily: "var(--font-stack-mono)", fontSize: 46, fontWeight: 800, color: broken ? c.bad : c.good, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>{days}</div>
            <div style={{ color: c.sub, fontSize: 12, marginTop: 4, textTransform: "uppercase", letterSpacing: "0.06em" }}>consecutive days</div>
          </div>
        )}
      </div>

      {/* ── Run log — the ledger made visible ── */}
      {runs.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, color: c.muted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>Verification log</div>
          <div style={{ border: `1px solid ${c.line}`, borderRadius: 12, overflow: "hidden" }}>
            {runs.slice(0, 30).map((r, i) => {
              const ok = r.outcome === "verified";
              const nArr = (r.arrival || []).filter((a) => a.arrived_value_matches).length;
              const nTot = (r.arrival || []).length;
              const open = openRun === r.id;
              const expandable = !ok || (r.arrival || []).length > 0;
              return (
                <div key={r.id} style={{ borderTop: i ? `1px solid ${c.line}` : "none", background: ok ? c.card : c.badbg }}>
                  <div onClick={() => expandable && setOpenRun(open ? "" : r.id)} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", cursor: expandable ? "pointer" : "default" }}>
                    <span style={{ width: 9, height: 9, borderRadius: "50%", background: ok ? c.good : c.bad, flexShrink: 0 }} />
                    <span style={{ color: c.ink, fontSize: 13, fontFamily: "var(--font-stack-mono)", minWidth: 130 }}>{fmt(r.started_at)}</span>
                    <span style={{ color: ok ? c.good : c.bad, fontSize: 12.5, fontWeight: 600, flex: 1 }}>{r.outcome}{r.mode === "dryrun" ? " · setup validation" : ""}</span>
                    {nTot > 0 && <span style={{ color: c.sub, fontSize: 12, fontFamily: "var(--font-stack-mono)" }}>{nArr}/{nTot} fields</span>}
                    {r.cleanup === "failed" && <span style={{ color: c.bad, fontSize: 11, fontWeight: 700 }}>CLEANUP FAILED</span>}
                    {expandable && <ChevronDown size={14} style={{ color: c.muted, transform: open ? "rotate(180deg)" : "none", transition: "transform 150ms" }} />}
                  </div>
                  {open && (r.arrival || []).length > 0 && (
                    <div style={{ padding: "4px 14px 12px 35px", display: "flex", flexDirection: "column", gap: 5 }}>
                      {r.arrival.map((a, j) => (
                        <div key={j} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
                          {a.arrived_value_matches ? <Check size={13} style={{ color: c.good }} /> : <X size={13} style={{ color: c.bad }} />}
                          <span style={{ color: c.ink, fontFamily: "var(--font-stack-mono)" }}>{a.field}</span>
                          <span style={{ color: c.muted }}>→ {a.crm_property}</span>
                          <span style={{ color: a.arrived_value_matches ? c.good : c.bad, fontSize: 12 }}>
                            {a.arrived_value_matches ? "arrived intact" : a.arrived ? "value mismatch" : "never arrived"}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Agency setup (connect CRM + enroll) ── */}
      {canManage && (
        <div style={{ marginTop: 16 }}>
          <button onClick={() => setSetup((s) => !s)} style={{ display: "inline-flex", alignItems: "center", gap: 7, background: "transparent", color: c.sub, border: `1px solid ${c.line}`, borderRadius: 9, padding: "8px 14px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
            <Plug size={14} /> {setup ? "Hide setup" : "Set up the tracer"}
          </button>
          {setup && <TracerSetup siteId={siteId} c={c} onChange={load} />}
        </div>
      )}
    </div>
  );
}

function TracerSetup({ siteId, c, onChange }: { siteId: string; c: typeof T.dark; onChange: () => void }) {
  const [crmType, setCrmType] = useState("hubspot");
  const [token, setToken] = useState("");
  const [crm, setCrm] = useState<{ connected: boolean; test_ok?: boolean; test_detail?: string; crm_type?: string } | null>(null);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [sel, setSel] = useState("");
  const [ack, setAck] = useState("");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const ACK = "I have excluded the test pattern from automations";

  const staff = async (): Promise<Record<string, string>> => {
    const t = await staffToken();
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (t) h.Authorization = `Bearer ${t}`;
    return h;
  };
  const refresh = useCallback(async () => {
    const h = await staff();
    setCrm(await fetch(`/api/sites/${siteId}/crm`, { headers: h }).then((r) => r.json()).catch(() => null));
    const cj = await fetch(`/api/sites/${siteId}/contracts`, { headers: h }).then((r) => r.json()).catch(() => ({ contracts: [] }));
    setContracts((cj.contracts || []).filter((x: Contract) => x.status === "confirmed"));
  }, [siteId]);
  useEffect(() => { refresh(); }, [refresh]);

  const connect = async () => {
    setBusy("connect"); setMsg(null);
    const creds = crmType === "hubspot" ? { token } : { api_key: token };
    const r = await fetch(`/api/sites/${siteId}/crm/connect`, { method: "POST", headers: await staff(), body: JSON.stringify({ crm_type: crmType, credentials: creds }) });
    const j = await r.json();
    setMsg(j.test_ok ? `✓ ${j.detail}` : `✗ ${j.detail || j.error}`); setToken(""); await refresh(); setBusy("");
  };
  const enroll = async () => {
    if (ack.trim() !== ACK) { setMsg("Type the acknowledgment exactly to enroll."); return; }
    setBusy("enroll"); setMsg(null);
    const r = await fetch(`/api/sites/${siteId}/tracer/enroll`, { method: "POST", headers: await staff(), body: JSON.stringify({ contract_key: sel, acknowledged: true }) });
    const j = await r.json();
    setMsg(r.ok ? "Enrolled. Run a dry-run to validate setup." : (j.error || "Enroll failed.")); setAck(""); setBusy(""); onChange();
  };
  const runNow = async () => {
    setBusy("run"); setMsg(null);
    const r = await fetch(`/api/sites/${siteId}/tracer/run-now`, { method: "POST", headers: await staff(), body: JSON.stringify({ contract_key: sel }) });
    const j = await r.json();
    setMsg(j.flag_off ? "TRACER_ENABLED is off — arm it in the backend first." : j.error ? j.error : `Run: ${j.outcome} (${j.mode})`);
    setBusy(""); onChange();
  };

  const inp: React.CSSProperties = { background: c.raised, border: `1px solid ${c.line}`, borderRadius: 8, padding: "8px 11px", fontSize: 13, color: c.ink };
  const btn = (bg: string, fg: string): React.CSSProperties => ({ display: "inline-flex", alignItems: "center", gap: 6, background: bg, color: fg, border: bg === "transparent" ? `1px solid ${c.line}` : "none", borderRadius: 8, padding: "8px 13px", fontSize: 13, fontWeight: 600, cursor: busy ? "wait" : "pointer" });

  return (
    <div style={{ marginTop: 12, border: `1px solid ${c.line}`, borderRadius: 12, padding: 16, background: c.raised }}>
      {/* 1. Connect CRM */}
      <div style={{ fontSize: 13, fontWeight: 700, color: c.ink, marginBottom: 8 }}>1 · Connect CRM {crm?.connected && <span style={{ color: crm.test_ok ? c.good : c.bad, fontWeight: 600, marginLeft: 6 }}>{crm.crm_type} {crm.test_ok ? "· token ok" : "· check token"}</span>}</div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <select value={crmType} onChange={(e) => setCrmType(e.target.value)} style={inp}><option value="hubspot">HubSpot</option><option value="ghl">GoHighLevel</option></select>
        <input value={token} onChange={(e) => setToken(e.target.value)} placeholder={crmType === "hubspot" ? "private-app token (contacts read/write)" : "location API key"} type="password" data-gramm="false" style={{ ...inp, minWidth: 280, flex: 1 }} />
        <button onClick={connect} disabled={!token || !!busy} style={btn(c.brand, "#fff")}>{busy === "connect" ? <Loader2 size={14} className="animate-spin" /> : <Plug size={14} />} Connect &amp; test</button>
      </div>

      {/* 2. Enroll a form */}
      <div style={{ fontSize: 13, fontWeight: 700, color: c.ink, margin: "16px 0 8px" }}>2 · Enroll a confirmed form</div>
      {contracts.length === 0 ? (
        <div style={{ color: c.sub, fontSize: 12.5 }}>Confirm a contract in the Contracts tab first.</div>
      ) : (
        <>
          <select value={sel} onChange={(e) => setSel(e.target.value)} style={{ ...inp, width: "100%", marginBottom: 8 }}>
            <option value="">Choose a form…</option>
            {contracts.map((ct) => <option key={ct.contract_key} value={ct.contract_key}>{ct.form_ref.form_id || ct.form_ref.page_url}</option>)}
          </select>
          <div style={{ color: c.sub, fontSize: 12.5, marginBottom: 6 }}>Before enrolling, exclude the tracer test pattern from your CRM automations. Then type: <b style={{ color: c.ink }}>{ACK}</b></div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input value={ack} onChange={(e) => setAck(e.target.value)} placeholder={ACK} data-gramm="false" style={{ ...inp, flex: 1, minWidth: 280 }} />
            <button onClick={enroll} disabled={!sel || !!busy} style={btn(c.brand, "#fff")}>{busy === "enroll" ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Enroll</button>
            <button onClick={runNow} disabled={!sel || !!busy} style={btn("transparent", c.sub)}>{busy === "run" ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} Dry-run</button>
          </div>
        </>
      )}
      {msg && <div style={{ marginTop: 10, fontSize: 12.5, color: msg.startsWith("✗") || msg.toLowerCase().includes("fail") || msg.toLowerCase().includes("off") ? c.bad : c.sub }}>{msg}</div>}
    </div>
  );
}
