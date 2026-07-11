"use client";

import React, { useEffect, useRef, useState } from "react";
import { Sparkles, X } from "lucide-react";

// One line per shipped change, newest first. Bump the top `id` on each deploy;
// a reader who hasn't seen it gets the "what's new" dot until they open this.
const ENTRIES: { id: string; date: string; text: string }[] = [
  { id: "2026-07-detail", date: "Jul 2026", text: "Detail pass: middle-truncated URLs, latency coloring, a live tab favicon, and keyboard triage (press ?)." },
  { id: "2026-07-history", date: "Jul 2026", text: "Time machine, clean-day streaks, and subway-style redirect route maps." },
  { id: "2026-07-evidence", date: "Jul 2026", text: "X-ray view, shareable client reports, and embeddable status badges." },
  { id: "2026-07-identity", date: "Jul 2026", text: "A new mission-control look — radar scan, ⌘K palette, mono data." },
];
const LATEST = ENTRIES[0].id;
const KEY = "linkspy:changelog-read";

export default function Changelog() {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      setUnread(localStorage.getItem(KEY) !== LATEST);
    } catch {
      setUnread(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    try { localStorage.setItem(KEY, LATEST); } catch { /* ignore */ }
    setUnread(false);
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    window.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); window.removeEventListener("keydown", onKey); };
  }, [open]);

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="What's new"
        style={{ position: "relative", display: "flex", alignItems: "center", padding: 8, borderRadius: 8, cursor: "pointer", background: "none", border: "none", color: "var(--text-muted)" }}
      >
        <Sparkles size={16} />
        {unread && (
          <span style={{ position: "absolute", top: 5, right: 5, width: 7, height: 7, borderRadius: "50%", background: "var(--signal)", boxShadow: "0 0 6px var(--signal)" }} />
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="What's new"
          style={{ position: "absolute", top: "calc(100% + 8px)", right: 0, zIndex: 120, width: 320, background: "var(--surface-raised)", border: "1px solid var(--border-strong)", borderRadius: "var(--radius-md)", boxShadow: "var(--elev-2)", padding: 14 }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <span className="font-display ds-text-primary" style={{ fontSize: "var(--text-body)", fontWeight: 700 }}>What&apos;s new</span>
            <button onClick={() => setOpen(false)} className="ds-text-muted" style={{ background: "none", border: "none", cursor: "pointer" }}><X size={15} /></button>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {ENTRIES.map((e) => (
              <div key={e.id} style={{ display: "flex", gap: 10 }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--signal)", marginTop: 6, flexShrink: 0 }} />
                <div>
                  <div className="ds-text-primary" style={{ fontSize: "var(--text-caption)" }}>{e.text}</div>
                  <div className="ds-text-muted font-mono" style={{ fontSize: 10, marginTop: 2 }}>{e.date}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
