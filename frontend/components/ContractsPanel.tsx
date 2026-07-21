"use client";

import { useCallback, useEffect, useState } from "react";
import { FileCheck2, Plus, Loader2, Check, ShieldAlert, ScanLine, X, Eye, EyeOff } from "lucide-react";

interface Field { name: string; required: boolean; kind: "visible" | "hidden"; populated_by: string; expected_crm_property: string | null; }
interface Contract {
  id: string; contract_key: string; version: number; status: string;
  form_ref: { page_url: string; form_id: string; selector: string };
  fields: Field[]; destination: { type: string; ids: Record<string, string> };
  events: Array<{ trigger: string; name: string }>; confirmed_by?: string; confirmed_at?: string;
}
interface Violation { kind: string; field: string; severity: string; consequence: string; }

const C = {
  ink: "var(--text-primary)", sub: "var(--text-secondary)", muted: "var(--text-muted)",
  card: "var(--surface-card)", raised: "var(--surface-raised)", line: "var(--border-subtle)",
  brand: "var(--signal)", good: "#4caf7d", high: "#f5a623", crit: "#e05c5c", critbg: "rgba(224,92,92,0.12)",
};

const destLabel = (d: Contract["destination"]) => {
  const t = d?.type || "unknown";
  const id = d?.ids?.portal_id || d?.ids?.form_id || "";
  return t === "unknown" ? "Destination unknown" : `${t}${id ? ` · ${id}` : ""}`;
};
const sevColor = (s: string) => (s === "critical" ? C.crit : s === "high" ? C.high : C.muted);

export default function ContractsPanel({ siteId }: { siteId: string }) {
  const [contracts, setContracts] = useState<Contract[] | null>(null);
  const [draftUrl, setDraftUrl] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [review, setReview] = useState<Contract | null>(null);       // draft under review
  const [drift, setDrift] = useState<Record<string, Violation[]>>({}); // contract_id → violations

  const auth = { "Content-Type": "application/json" };

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/sites/${siteId}/contracts`);
      const j = await res.json();
      setContracts(j.contracts || []);
    } catch { setContracts([]); }
  }, [siteId]);
  useEffect(() => { load(); }, [load]);

  const draft = async () => {
    if (!draftUrl.trim()) return;
    setBusy("draft"); setErr(null);
    try {
      const res = await fetch(`/api/sites/${siteId}/contracts/draft`, {
        method: "POST", headers: auth, body: JSON.stringify({ page_url: draftUrl.trim() }) });
      const j = await res.json();
      if (!res.ok) throw new Error(j.error || "Couldn't draft a contract.");
      setReview(j.contract); setDraftUrl("");
    } catch (e) { setErr(e instanceof Error ? e.message : "Draft failed."); } finally { setBusy(""); }
  };

  const confirm = async (c: Contract) => {
    setBusy("confirm"); setErr(null);
    try {
      const res = await fetch(`/api/sites/${siteId}/contracts/${c.contract_key}/confirm`, {
        method: "POST", headers: auth,
        body: JSON.stringify({ form_ref: c.form_ref, fields: c.fields, destination: c.destination, events: c.events }) });
      if (!res.ok) { const j = await res.json(); throw new Error(j.error || "Confirm failed."); }
      setReview(null); await load();
    } catch (e) { setErr(e instanceof Error ? e.message : "Confirm failed."); } finally { setBusy(""); }
  };

  const checkDrift = async (c: Contract) => {
    setBusy("drift:" + c.id); setErr(null);
    try {
      const res = await fetch(`/api/sites/${siteId}/contracts/drift-check`, {
        method: "POST", headers: auth, body: JSON.stringify({ page_url: c.form_ref.page_url }) });
      const j = await res.json();
      if (!res.ok) throw new Error(j.error || "Drift check failed.");
      const mine = (j.results || []).find((r: { contract_id: string }) => r.contract_id === c.id);
      setDrift((d) => ({ ...d, [c.id]: mine?.violations || [] }));
    } catch (e) { setErr(e instanceof Error ? e.message : "Drift check failed."); } finally { setBusy(""); }
  };

  const editReviewField = (i: number, prop: string) =>
    setReview((r) => r ? { ...r, fields: r.fields.map((f, j) => j === i ? { ...f, expected_crm_property: prop || null } : f) } : r);

  const confirmed = (contracts || []).filter((c) => c.status === "confirmed");
  const drafts = (contracts || []).filter((c) => c.status === "draft");

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <FileCheck2 size={18} style={{ color: C.brand }} />
          <span style={{ fontFamily: "var(--font-stack-display)", fontWeight: 700, fontSize: 18, color: C.ink }}>Lead delivery contracts</span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input value={draftUrl} onChange={(e) => setDraftUrl(e.target.value)} placeholder="https://site.com/contact"
            data-gramm="false" spellCheck={false}
            style={{ background: C.raised, border: `1px solid ${C.line}`, borderRadius: 9, padding: "8px 12px", fontSize: 13, color: C.ink, minWidth: 240 }} />
          <button onClick={draft} disabled={!!busy} style={btn(C.brand, "#fff", busy)}>
            {busy === "draft" ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Draft from page
          </button>
        </div>
      </div>
      {err && <div style={{ color: C.crit, fontSize: 13, marginBottom: 12 }}>{err}</div>}

      {/* ── Draft review (side-by-side; confirm in ≤60s) ── */}
      {review && (
        <div style={{ border: `1px solid ${C.brand}`, borderRadius: 14, padding: 18, marginBottom: 16, background: C.raised }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <div style={{ fontWeight: 700, color: C.ink, fontSize: 15 }}>Review draft contract</div>
            <button onClick={() => setReview(null)} style={{ background: "none", border: "none", color: C.muted, cursor: "pointer" }}><X size={16} /></button>
          </div>
          <div style={{ color: C.sub, fontSize: 13, marginBottom: 6 }}>{review.form_ref.page_url}</div>
          <div style={{ display: "inline-flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
            <span style={chip(C)}>{destLabel(review.destination)}</span>
            <span style={chip(C)}>{review.fields.length} fields</span>
            {review.events.map((e, i) => <span key={i} style={chip(C)}>{e.trigger}:{e.name}</span>)}
          </div>
          <div style={{ border: `1px solid ${C.line}`, borderRadius: 10, overflow: "hidden" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1.4fr 0.8fr 0.8fr 1.4fr", gap: 0, fontSize: 11, color: C.muted, padding: "8px 12px", background: C.card, textTransform: "uppercase", letterSpacing: "0.04em" }}>
              <span>Field (observed)</span><span>Kind</span><span>Required</span><span>Maps to CRM property</span>
            </div>
            {review.fields.map((f, i) => (
              <div key={i} style={{ display: "grid", gridTemplateColumns: "1.4fr 0.8fr 0.8fr 1.4fr", gap: 0, alignItems: "center", padding: "8px 12px", borderTop: `1px solid ${C.line}`, fontSize: 13 }}>
                <span style={{ color: C.ink, fontFamily: "var(--font-stack-mono)" }}>{f.name}</span>
                <span style={{ color: C.sub, display: "inline-flex", alignItems: "center", gap: 4 }}>
                  {f.kind === "hidden" ? <EyeOff size={12} /> : <Eye size={12} />}{f.kind}{f.kind === "hidden" && f.populated_by === "js" ? " · js" : ""}
                </span>
                <span style={{ color: f.required ? C.ink : C.muted }}>{f.required ? "required" : "optional"}</span>
                <input value={f.expected_crm_property || ""} onChange={(e) => editReviewField(i, e.target.value)}
                  placeholder={f.kind === "hidden" ? "—" : "property"} data-gramm="false"
                  style={{ background: C.raised, border: `1px solid ${C.line}`, borderRadius: 6, padding: "4px 8px", fontSize: 12.5, color: C.ink }} />
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
            <button onClick={() => confirm(review)} disabled={!!busy} style={btn(C.good, "#04120a", busy)}>
              {busy === "confirm" ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Confirm contract
            </button>
            <button onClick={() => setReview(null)} style={btn("transparent", C.sub, "", C.line)}>Discard</button>
          </div>
        </div>
      )}

      {/* ── Drafts awaiting review ── */}
      {drafts.filter((d) => d.id !== review?.id).map((d) => (
        <div key={d.id} style={{ border: `1px solid ${C.line}`, borderRadius: 12, padding: "12px 16px", marginBottom: 10, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <div style={{ minWidth: 0 }}>
            <span style={{ background: "rgba(79,70,229,0.15)", color: C.brand, fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 999, marginRight: 8 }}>DRAFT</span>
            <span style={{ color: C.sub, fontSize: 13 }}>{d.form_ref.page_url}</span>
          </div>
          <button onClick={() => setReview(d)} style={btn(C.brand, "#fff", "")}>Review</button>
        </div>
      ))}

      {/* ── Confirmed contracts — the calm primary surface ── */}
      {contracts === null ? (
        <div className="animate-pulse" style={{ height: 90, borderRadius: 12, background: C.raised, border: `1px solid ${C.line}` }} />
      ) : confirmed.length === 0 && drafts.length === 0 && !review ? (
        <div style={{ border: `1px dashed ${C.line}`, borderRadius: 16, padding: "40px 24px", textAlign: "center", background: C.raised }}>
          <FileCheck2 size={28} style={{ color: C.brand, marginBottom: 12 }} />
          <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 17, fontWeight: 600, color: C.ink }}>No contracts yet</div>
          <div style={{ color: C.sub, fontSize: 14, marginTop: 6, maxWidth: 420, marginInline: "auto" }}>
            Draft a contract from a form to define what an intact lead looks like — the record we verify against every day.
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 14 }}>
          {confirmed.map((c) => {
            const v = drift[c.id];
            const bad = v && v.length > 0;
            return (
              <div key={c.id} style={{ borderRadius: 14, background: C.card, border: `1px solid ${bad ? C.crit : C.line}`, padding: 16 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                  <span style={{ color: C.ink, fontSize: 14, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {c.form_ref.form_id || new URL(c.form_ref.page_url).pathname}
                  </span>
                  {!bad && <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: C.good, fontSize: 12, flexShrink: 0 }}><Check size={13} /> Confirmed</span>}
                </div>
                <div style={{ color: C.muted, fontSize: 12, marginTop: 3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.form_ref.page_url}</div>
                <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                  <span style={chip(C)}>{destLabel(c.destination)}</span>
                  <span style={chip(C)}>{c.fields.length} fields</span>
                  <span style={chip(C)}>v{c.version}</span>
                </div>
                {bad && (
                  <div style={{ marginTop: 12, background: C.critbg, border: `1px solid ${C.crit}`, borderRadius: 10, padding: "10px 12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, color: C.crit, fontWeight: 700, fontSize: 13, marginBottom: 6 }}>
                      <ShieldAlert size={14} /> {v.length} drift violation{v.length === 1 ? "" : "s"}
                    </div>
                    {v.map((x, i) => (
                      <div key={i} style={{ fontSize: 12.5, color: C.sub, marginTop: 4 }}>
                        <span style={{ color: sevColor(x.severity), fontWeight: 700, textTransform: "uppercase", fontSize: 10, marginRight: 6 }}>{x.severity}</span>
                        {x.consequence}
                      </div>
                    ))}
                  </div>
                )}
                <button onClick={() => checkDrift(c)} disabled={!!busy}
                  style={{ ...btn("transparent", C.sub, busy === "drift:" + c.id ? "x" : "", C.line), marginTop: 12, fontSize: 12.5 }}>
                  {busy === "drift:" + c.id ? <Loader2 size={13} className="animate-spin" /> : <ScanLine size={13} />} Check drift
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function btn(bg: string, fg: string, busy: string, border?: string): React.CSSProperties {
  return { display: "inline-flex", alignItems: "center", gap: 6, background: bg, color: fg,
    border: border ? `1px solid ${border}` : "none", borderRadius: 9, padding: "8px 13px",
    fontSize: 13, fontWeight: 600, cursor: busy ? "wait" : "pointer", opacity: busy ? 0.7 : 1 };
}
function chip(c: typeof C): React.CSSProperties {
  return { background: c.raised, border: `1px solid ${c.line}`, color: c.sub, fontSize: 11.5,
    padding: "3px 9px", borderRadius: 999, fontFamily: "var(--font-stack-mono)" };
}
