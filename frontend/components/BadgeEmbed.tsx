"use client";

import React, { useState } from "react";
import { Copy, Check } from "lucide-react";

// Live status badge + a copy-embed snippet for a site's settings.
export default function BadgeEmbed({ siteId, siteUrl }: { siteId: string; siteUrl: string }) {
  const [copied, setCopied] = useState<string | null>(null);

  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const badgeUrl = `${origin}/api/sites/${siteId}/badge.svg`;
  const html = `<a href="${siteUrl}"><img src="${badgeUrl}" alt="LinkSpy status" /></a>`;
  const markdown = `[![LinkSpy status](${badgeUrl})](${siteUrl})`;

  const copy = async (text: string, key: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      setTimeout(() => setCopied(null), 800);
    } catch {
      /* ignore */
    }
  };

  const Snippet = ({ label, value, k }: { label: string; value: string; k: string }) => (
    <div style={{ marginTop: 12 }}>
      <div className="ds-text-muted font-mono" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>{label}</div>
      <div style={{ display: "flex", gap: 6 }}>
        <code className="font-mono" style={{ flex: 1, minWidth: 0, background: "rgba(3,8,9,0.5)", border: "1px solid var(--border-subtle)", color: "var(--text-secondary)", borderRadius: "var(--radius-sm)", padding: "8px 10px", fontSize: 12, overflowX: "auto", whiteSpace: "nowrap" }}>{value}</code>
        <button className="ds-btn-ghost" onClick={() => copy(value, k)} style={{ padding: "0 12px", flexShrink: 0 }}>
          {copied === k ? <Check size={15} /> : <Copy size={15} />}
        </button>
      </div>
    </div>
  );

  return (
    <div className="ds-card ds-card-pad">
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 4 }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={badgeUrl} alt="LinkSpy status badge" style={{ height: 20 }} />
      </div>
      <p className="ds-text-secondary" style={{ fontSize: "var(--text-caption)", marginTop: 8 }}>
        Live health badge — updates within minutes of each scan. Paste it into a README or status page.
      </p>
      <Snippet label="Markdown" value={markdown} k="md" />
      <Snippet label="HTML" value={html} k="html" />
    </div>
  );
}
