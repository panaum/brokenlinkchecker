"use client";

import React, { useState, useCallback } from "react";
import { Share2, Copy, Check, X, Loader2 } from "lucide-react";
import { ShareResult } from "@/types";

// Creates a public, revocable share link for a scan and lets the user copy or
// revoke it. No link exists until the user asks for one.
export default function ShareButton({ scanId }: { scanId: string }) {
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [share, setShare] = useState<ShareResult | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = useCallback(async () => {
    setOpen(true);
    if (share || creating) return;
    setCreating(true);
    setError(null);
    try {
      const res = await fetch(`/api/scans/${scanId}/share`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not create a share link.");
      setShare(data as ShareResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create a share link.");
    } finally {
      setCreating(false);
    }
  }, [scanId, share, creating]);

  const copy = useCallback(async () => {
    if (!share) return;
    try {
      await navigator.clipboard.writeText(share.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 800);
    } catch {
      /* ignore */
    }
  }, [share]);

  const revoke = useCallback(async () => {
    if (!share) return;
    await fetch(`/api/share/${share.token}`, { method: "DELETE" }).catch(() => {});
    setShare(null);
    setOpen(false);
  }, [share]);

  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <button className="ds-btn-ghost" onClick={create} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
        <Share2 size={15} /> Share report
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Share report link"
          style={{
            position: "absolute", top: "calc(100% + 8px)", right: 0, zIndex: 40, width: 360,
            background: "var(--surface-raised)", border: "1px solid var(--border-strong)",
            borderRadius: "var(--radius-md)", boxShadow: "var(--elev-2)", padding: 14,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
            <span className="ds-text-primary" style={{ fontSize: "var(--text-body)", fontWeight: 600 }}>Public report link</span>
            <button onClick={() => setOpen(false)} className="ds-text-muted" style={{ background: "none", border: "none", cursor: "pointer" }}><X size={16} /></button>
          </div>

          {creating ? (
            <div className="ds-text-secondary" style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "var(--text-caption)" }}>
              <Loader2 size={14} className="animate-spin" /> Creating link…
            </div>
          ) : error ? (
            <div className="ds-status ds-status-broken" style={{ fontSize: "var(--text-caption)" }}><span className="ds-status-dot" />{error}</div>
          ) : share ? (
            <>
              <p className="ds-text-muted" style={{ fontSize: "var(--text-caption)", marginBottom: 8, lineHeight: 1.5 }}>
                Anyone with this link can view a read-only report. No login. Revoke it any time.
              </p>
              <div style={{ display: "flex", gap: 6 }}>
                <input
                  readOnly
                  value={share.url}
                  onFocus={(e) => e.currentTarget.select()}
                  className="font-mono"
                  style={{ flex: 1, minWidth: 0, background: "rgba(3,8,9,0.5)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)", borderRadius: "var(--radius-sm)", padding: "8px 10px", fontSize: 12 }}
                />
                <button className="ds-btn-primary" onClick={copy} style={{ padding: "0 12px" }}>
                  {copied ? <Check size={15} /> : <Copy size={15} />}
                </button>
              </div>
              <button onClick={revoke} className="ds-text-muted" style={{ marginTop: 10, background: "none", border: "none", cursor: "pointer", fontSize: "var(--text-caption)", color: "var(--status-broken)" }}>
                Revoke this link
              </button>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}
