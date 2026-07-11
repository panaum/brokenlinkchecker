"use client";

import React, { useEffect, useState, useRef, useCallback } from "react";

// Keyboard triage for a findings list. Rows opt in with [data-finding-row].
//   j / k   next / prev finding (focus + scroll)
//   e / f   open/close the fix for the focused finding
//   r       re-check the focused finding
//   c       copy the client message
//   x       open X-ray focused on this finding
//   ?       shortcuts overlay
// Ignores keystrokes while typing in an input; never fires with a modifier held.
const SHORTCUTS: [string, string][] = [
  ["j / k", "Next / previous finding"],
  ["e or f", "Open / close the fix"],
  ["r", "Re-check this finding"],
  ["c", "Copy client message"],
  ["x", "X-ray this finding"],
  ["?", "Toggle this help"],
  ["Esc", "Clear focus / close"],
];

function rows(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>("[data-finding-row]"));
}

export default function KeyboardTriage() {
  const [helpOpen, setHelpOpen] = useState(false);
  const activeRef = useRef(-1);

  const paint = useCallback((idx: number) => {
    const all = rows();
    all.forEach((el, i) => {
      if (i === idx) el.setAttribute("data-triage-active", "true");
      else el.removeAttribute("data-triage-active");
    });
    const el = all[idx];
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  const clickInActive = useCallback((triage: string) => {
    const el = rows()[activeRef.current];
    if (!el) return;
    el.querySelector<HTMLButtonElement>(`[data-triage="${triage}"]`)?.click();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      const tag = t?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || t?.isContentEditable) return;

      if (e.key === "?") { e.preventDefault(); setHelpOpen((v) => !v); return; }
      if (e.key === "Escape") {
        if (helpOpen) setHelpOpen(false);
        activeRef.current = -1;
        rows().forEach((el) => el.removeAttribute("data-triage-active"));
        return;
      }

      const all = rows();
      if (all.length === 0) return;

      switch (e.key) {
        case "j":
          e.preventDefault();
          activeRef.current = Math.min(all.length - 1, activeRef.current + 1);
          paint(activeRef.current);
          break;
        case "k":
          e.preventDefault();
          activeRef.current = Math.max(0, activeRef.current < 0 ? 0 : activeRef.current - 1);
          paint(activeRef.current);
          break;
        case "e":
        case "f":
          if (activeRef.current >= 0) { e.preventDefault(); clickInActive("fix"); }
          break;
        case "r":
          if (activeRef.current >= 0) { e.preventDefault(); clickInActive("recheck"); }
          break;
        case "c":
          if (activeRef.current >= 0) { e.preventDefault(); clickInActive("copy"); }
          break;
        case "x":
          if (activeRef.current >= 0) {
            e.preventDefault();
            const el = all[activeRef.current];
            window.dispatchEvent(new CustomEvent("linkspy:xray", { detail: { url: el.getAttribute("data-finding-url") } }));
          }
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [helpOpen, paint, clickInActive]);

  if (!helpOpen) return null;

  return (
    <div
      className="no-print"
      onClick={() => setHelpOpen(false)}
      style={{ position: "fixed", inset: 0, zIndex: 210, background: "rgba(3,8,9,0.6)", backdropFilter: "blur(4px)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}
    >
      <div className="ds-card ds-card-pad" onClick={(e) => e.stopPropagation()} style={{ width: "100%", maxWidth: 380 }}>
        <div className="font-display ds-text-primary" style={{ fontSize: "var(--text-heading)", fontWeight: 700, marginBottom: 14 }}>
          Keyboard triage
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {SHORTCUTS.map(([key, desc]) => (
            <div key={key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
              <span className="ds-text-secondary" style={{ fontSize: "var(--text-body)" }}>{desc}</span>
              <kbd className="font-mono" style={{ fontSize: 12, color: "var(--text-primary)", border: "1px solid var(--border-subtle)", borderRadius: 6, padding: "2px 8px", flexShrink: 0 }}>{key}</kbd>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
