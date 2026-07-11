"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import { Search, Radar, LayoutDashboard, Wrench, Settings, RotateCw, Globe } from "lucide-react";

interface Site {
  id: string;
  url: string;
  name?: string;
  last_scanned_at?: string;
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

// Global command palette. ⌘K / Ctrl-K from anywhere; every page and every
// monitored site reachable in two keystrokes.
export default function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [sites, setSites] = useState<Site[]>([]);

  // Toggle on ⌘K / Ctrl-K, and open on an explicit event (the nav button).
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

  // Load monitored sites once the palette is first opened (cheap, cached by the
  // browser afterwards). Recently-scanned first.
  useEffect(() => {
    if (!open || sites.length) return;
    fetch("/api/dashboard")
      .then((r) => (r.ok ? r.json() : { sites: [] }))
      .then((d: { sites?: Site[] }) => {
        const list = [...(d.sites ?? [])].sort(
          (a, b) => new Date(b.last_scanned_at ?? 0).getTime() - new Date(a.last_scanned_at ?? 0).getTime(),
        );
        setSites(list);
      })
      .catch(() => {});
  }, [open, sites.length]);

  const go = useCallback(
    (href: string) => {
      setOpen(false);
      router.push(href);
    },
    [router],
  );

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Command palette"
      className="cmdk-root"
    >
      <div className="cmdk-input-row">
        <Search size={16} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
        <Command.Input autoFocus placeholder="Search actions and sites…" className="cmdk-input" />
        <kbd className="cmdk-kbd">ESC</kbd>
      </div>
      <Command.List className="cmdk-list">
        <Command.Empty className="cmdk-empty">No matches.</Command.Empty>

        <Command.Group heading="Actions" className="cmdk-group">
          <Command.Item className="cmdk-item" onSelect={() => go("/")} keywords={["scan", "new", "audit"]}>
            <Radar size={15} /> Scan a site
          </Command.Item>
          <Command.Item className="cmdk-item" onSelect={() => go("/dashboard")} keywords={["sites", "overview", "monitor"]}>
            <LayoutDashboard size={15} /> Open dashboard
          </Command.Item>
          <Command.Item className="cmdk-item" onSelect={() => go("/self-heal")} keywords={["fix", "pr", "pull request"]}>
            <Wrench size={15} /> Self-heal
          </Command.Item>
        </Command.Group>

        {sites.length > 0 && (
          <Command.Group heading="Sites" className="cmdk-group">
            {sites.map((s) => {
              const label = s.name?.trim() || domainOf(s.url);
              return (
                <React.Fragment key={s.id}>
                  <Command.Item
                    className="cmdk-item"
                    value={`rescan ${label} ${domainOf(s.url)}`}
                    onSelect={() => go(`/?url=${encodeURIComponent(s.url)}`)}
                  >
                    <RotateCw size={15} /> Re-scan <span className="mono cmdk-dim">{domainOf(s.url)}</span>
                  </Command.Item>
                  <Command.Item
                    className="cmdk-item"
                    value={`settings ${label} ${domainOf(s.url)}`}
                    onSelect={() => go(`/dashboard/${s.id}`)}
                  >
                    <Settings size={15} /> {label} <span className="cmdk-dim">settings</span>
                  </Command.Item>
                </React.Fragment>
              );
            })}
          </Command.Group>
        )}

        {sites.length === 0 && (
          <Command.Group heading="Sites" className="cmdk-group">
            <Command.Item className="cmdk-item" onSelect={() => go("/dashboard")}>
              <Globe size={15} /> <span className="cmdk-dim">No monitored sites yet — open the dashboard to add one</span>
            </Command.Item>
          </Command.Group>
        )}
      </Command.List>
    </Command.Dialog>
  );
}
