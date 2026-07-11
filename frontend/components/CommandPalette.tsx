"use client";

import React, { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import { Search, Radar, LayoutDashboard, Wrench, Settings, RotateCw } from "lucide-react";

interface Site {
  id: string;
  url: string;
  name?: string;
  last_scanned_at?: string;
}

interface Item {
  id: string;
  label: string;
  hint?: string;
  keywords: string;
  icon: React.ReactNode;
  href: string;
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

// Global command palette — a self-contained modal (no external dialog lib), so
// it always renders. ⌘K / Ctrl-K, or the nav button's event, opens it.
export default function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [sites, setSites] = useState<Site[]>([]);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    const onOpen = () => setOpen(true);
    document.addEventListener("keydown", onKey);
    window.addEventListener("linkspy:open-command-palette", onOpen);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("linkspy:open-command-palette", onOpen);
    };
  }, []);

  // Reset + focus when opened; load sites once.
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActive(0);
    const t = setTimeout(() => inputRef.current?.focus(), 20);
    if (!sites.length) {
      fetch("/api/dashboard")
        .then((r) => (r.ok ? r.json() : { sites: [] }))
        .then((d: { sites?: Site[] }) => {
          const list = [...(d.sites ?? [])].sort(
            (a, b) => new Date(b.last_scanned_at ?? 0).getTime() - new Date(a.last_scanned_at ?? 0).getTime(),
          );
          setSites(list);
        })
        .catch(() => {});
    }
    return () => clearTimeout(t);
  }, [open, sites.length]);

  const items: Item[] = useMemo(() => {
    const base: Item[] = [
      { id: "scan", label: "Scan a site", keywords: "scan new audit link", icon: <Radar size={16} />, href: "/" },
      { id: "dashboard", label: "Open dashboard", keywords: "sites overview monitor", icon: <LayoutDashboard size={16} />, href: "/dashboard" },
      { id: "selfheal", label: "Self-heal", keywords: "fix pr pull request", icon: <Wrench size={16} />, href: "/self-heal" },
    ];
    for (const s of sites) {
      const label = s.name?.trim() || domainOf(s.url);
      base.push({ id: `rescan-${s.id}`, label: `Re-scan ${domainOf(s.url)}`, keywords: `rescan scan ${label} ${domainOf(s.url)}`, icon: <RotateCw size={16} />, href: `/?url=${encodeURIComponent(s.url)}` });
      base.push({ id: `settings-${s.id}`, label: `${label} settings`, hint: "settings", keywords: `settings ${label} ${domainOf(s.url)}`, icon: <Settings size={16} />, href: `/dashboard/${s.id}` });
    }
    return base;
  }, [sites]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((i) => (i.label + " " + i.keywords).toLowerCase().includes(q));
  }, [items, query]);

  const go = useCallback((href: string) => {
    setOpen(false);
    router.push(href);
  }, [router]);

  const onInputKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { setOpen(false); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(filtered.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); const it = filtered[active]; if (it) go(it.href); }
  };

  useEffect(() => {
    if (active >= filtered.length) setActive(0);
  }, [filtered.length, active]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-label="Command palette"
      onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false); }}
      style={{
        position: "fixed", inset: 0, zIndex: 300,
        background: "rgba(6,4,12,0.6)", backdropFilter: "blur(4px)",
        display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "14vh 16px 16px",
      }}
    >
      <div
        style={{
          width: "min(92vw, 580px)", background: "var(--surface-raised)",
          border: "1px solid var(--border-strong)", borderRadius: "var(--radius-lg)",
          boxShadow: "var(--elev-3)", overflow: "hidden",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 16px", borderBottom: "1px solid var(--border-subtle)" }}>
          <Search size={16} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => { setQuery(e.target.value); setActive(0); }}
            onKeyDown={onInputKey}
            placeholder="Search actions and sites…"
            style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: "var(--text-primary)", fontSize: 15, fontFamily: "var(--font-stack-body)" }}
          />
          <kbd className="font-mono" style={{ fontSize: 10, color: "var(--text-muted)", border: "1px solid var(--border-subtle)", borderRadius: 5, padding: "2px 6px" }}>ESC</kbd>
        </div>

        <div ref={listRef} style={{ maxHeight: 360, overflowY: "auto", padding: 8 }}>
          {filtered.length === 0 ? (
            <div className="ds-text-muted" style={{ padding: 24, textAlign: "center", fontSize: "var(--text-body)" }}>No matches.</div>
          ) : (
            filtered.map((it, i) => (
              <button
                key={it.id}
                onMouseEnter={() => setActive(i)}
                onClick={() => go(it.href)}
                style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 10,
                  padding: "10px 12px", borderRadius: "var(--radius-sm)", cursor: "pointer",
                  border: "none", textAlign: "left", fontSize: "var(--text-body)",
                  color: "var(--text-primary)", fontFamily: "var(--font-stack-body)",
                  background: i === active ? "rgba(168,85,247,0.16)" : "transparent",
                  boxShadow: i === active ? "inset 2px 0 0 var(--signal)" : "none",
                }}
              >
                <span style={{ color: "var(--text-secondary)", display: "flex", flexShrink: 0 }}>{it.icon}</span>
                <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.label}</span>
                {it.hint && <span className="ds-text-muted" style={{ fontSize: "var(--text-caption)" }}>{it.hint}</span>}
              </button>
            ))
          )}
          {sites.length === 0 && (
            <div className="ds-text-muted" style={{ padding: "8px 12px", fontSize: "var(--text-caption)" }}>
              No monitored sites yet — add one from the dashboard.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
