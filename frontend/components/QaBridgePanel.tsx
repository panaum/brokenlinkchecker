"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Link2, Trash2, Plus, KeyRound, Copy, Check } from "lucide-react";

// Agency-internal admin: link a QA-app deliverable (its page ref) to this
// monitored site so the QA app can read live "still true today" status. Also
// mints/rotates the read-only service key the QA app authenticates with.
// Explicit mapping only — no name-guessing against the QA app's messy list.

interface QaMap { id: string; qa_page_ref: string; page_url: string | null; created_at: string; created_by?: string }
interface QaKey { id: string; label: string | null; key_prefix: string; created_at: string; last_used_at: string | null; revoked_at: string | null }

export default function QaBridgePanel({ siteId }: { siteId: string }) {
  const [maps, setMaps] = useState<QaMap[]>([]);
  const [keys, setKeys] = useState<QaKey[]>([]);
  const [ref, setRef] = useState("");
  const [pageUrl, setPageUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      const [m, k] = await Promise.all([
        fetch(`/api/sites/${siteId}/qa-bridge/maps`, { cache: "no-store" }).then((r) => r.json()),
        fetch(`/api/qa-bridge/keys`, { cache: "no-store" }).then((r) => r.json()),
      ]);
      setMaps(m.maps ?? []);
      setKeys(k.keys ?? []);
    } catch { /* leave as-is; panel is best-effort */ }
  }, [siteId]);

  useEffect(() => { load(); }, [load]);

  const addMap = async () => {
    const ref_ = ref.trim();
    if (!ref_) return;
    setBusy(true); setErr(null);
    try {
      const res = await fetch(`/api/sites/${siteId}/qa-bridge/maps`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ qa_page_ref: ref_, page_url: pageUrl.trim() || undefined }),
      });
      const body = await res.json();
      if (!res.ok) { setErr(body.error || "Couldn't link that deliverable."); return; }
      setRef(""); setPageUrl(""); await load();
    } finally { setBusy(false); }
  };

  const unlink = async (id: string) => {
    await fetch(`/api/sites/${siteId}/qa-bridge/maps/${id}`, { method: "DELETE" });
    await load();
  };

  const createKey = async () => {
    setBusy(true); setErr(null);
    try {
      const res = await fetch(`/api/qa-bridge/keys`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: "QA Dashboard" }),
      });
      const body = await res.json();
      if (!res.ok) { setErr(body.error || "Couldn't create a key."); return; }
      setNewKey(body.raw_token); setCopied(false); await load();
    } finally { setBusy(false); }
  };

  const revokeKey = async (id: string) => {
    await fetch(`/api/qa-bridge/keys/${id}`, { method: "DELETE" });
    await load();
  };

  const copyKey = () => {
    if (!newKey) return;
    navigator.clipboard?.writeText(newKey).then(() => { setCopied(true); }).catch(() => {});
  };

  const activeKeys = keys.filter((k) => !k.revoked_at);

  return (
    <div className="ds-card ds-card-pad" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* ── Deliverable mapping ── */}
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <Link2 size={16} style={{ color: "var(--signal)" }} />
          <span className="ds-text-primary" style={{ fontWeight: 600, fontSize: "var(--text-body)" }}>Linked QA deliverables</span>
        </div>
        <p className="ds-text-secondary" style={{ fontSize: "var(--text-caption)", marginBottom: 12 }}>
          Paste the QA app&apos;s page reference to link it to this site. The QA app then shows each delivery check&apos;s live status. Add a page URL for page-level precision.
        </p>

        {maps.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 12 }}>
            {maps.map((m) => (
              <div key={m.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "8px 12px", background: "var(--surface-sunken)", borderRadius: 8 }}>
                <div style={{ minWidth: 0 }}>
                  <span className="ds-text-primary font-mono" style={{ fontSize: "var(--text-caption)", fontWeight: 600 }}>{m.qa_page_ref}</span>
                  {m.page_url && <span className="ds-text-muted font-mono" style={{ fontSize: "var(--text-caption)", marginLeft: 8, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>· {m.page_url}</span>}
                </div>
                <button onClick={() => unlink(m.id)} className="ds-text-muted" title="Unlink" style={{ background: "none", border: "none", cursor: "pointer", flexShrink: 0, display: "inline-flex" }}>
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="QA page reference"
            className="ds-input" style={{ flex: 2, minWidth: 160 }} />
          <input value={pageUrl} onChange={(e) => setPageUrl(e.target.value)} placeholder="Page URL (optional)"
            className="ds-input" style={{ flex: 3, minWidth: 180 }} />
          <button onClick={addMap} disabled={busy || !ref.trim()} className="ds-btn-primary" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Plus size={14} /> Link
          </button>
        </div>
      </div>

      {/* ── Service key ── */}
      <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <KeyRound size={16} style={{ color: "var(--signal)" }} />
          <span className="ds-text-primary" style={{ fontWeight: 600, fontSize: "var(--text-body)" }}>QA Dashboard service key</span>
        </div>
        <p className="ds-text-secondary" style={{ fontSize: "var(--text-caption)", marginBottom: 12 }}>
          Read-only key the QA app uses to fetch status. Stored only as a hash — shown once at creation. Rotate any time; revoking is instant.
        </p>

        {newKey && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 12px", background: "var(--surface-sunken)", border: "1px solid var(--signal)", borderRadius: 8, marginBottom: 12 }}>
            <code className="font-mono" style={{ flex: 1, fontSize: "var(--text-caption)", wordBreak: "break-all", color: "var(--text-primary)" }}>{newKey}</code>
            <button onClick={copyKey} className="ds-btn-ghost" style={{ display: "inline-flex", alignItems: "center", gap: 5, flexShrink: 0 }}>
              {copied ? <><Check size={13} /> Copied</> : <><Copy size={13} /> Copy</>}
            </button>
          </div>
        )}
        {newKey && <p className="ds-text-muted" style={{ fontSize: "var(--text-caption)", marginBottom: 12 }}>Copy this now — you won&apos;t see it again.</p>}

        {activeKeys.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 12 }}>
            {activeKeys.map((k) => (
              <div key={k.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "8px 12px", background: "var(--surface-sunken)", borderRadius: 8 }}>
                <span className="ds-text-secondary font-mono" style={{ fontSize: "var(--text-caption)" }}>
                  {k.key_prefix}… {k.last_used_at ? "· used" : "· never used"}
                </span>
                <button onClick={() => revokeKey(k.id)} className="ds-text-muted" title="Revoke" style={{ background: "none", border: "none", cursor: "pointer", flexShrink: 0, display: "inline-flex" }}>
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}

        <button onClick={createKey} disabled={busy} className="ds-btn-ghost" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Plus size={14} /> {activeKeys.length ? "Rotate key" : "Create key"}
        </button>
      </div>

      {err && <p style={{ color: "var(--status-broken)", fontSize: "var(--text-caption)" }}>{err}</p>}
    </div>
  );
}
