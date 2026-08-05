"use client";

import React, { useEffect, useState } from "react";
import { FlaskConical, ExternalLink } from "lucide-react";

// DELIVERY PRESENCE — one quiet line in the Site Detail header: what the QA app
// is doing with this site right now.
//
// Renders NOTHING unless there is something to say: flag off, nothing in QA,
// bridge unreachable with no cache — all of them are "no line". The flag and
// the bridge key live server-side in /api/presence/delivery; this component
// receives only derived, non-secret text and a pre-signed handoff URL.

type Data = {
  enabled: boolean;
  count?: number;
  testers?: string[];
  open_in_qa_url?: string | null;
  stale?: boolean;
};

export default function DeliveryPresenceLine({ siteId }: { siteId: string }) {
  const [data, setData] = useState<Data | null>(null);

  useEffect(() => {
    let live = true;
    const load = () =>
      fetch(`/api/presence/delivery?site_id=${encodeURIComponent(siteId)}`, { cache: "no-store" })
        .then((r) => r.json())
        .then((d) => { if (live) setData(d); })
        .catch(() => { if (live) setData({ enabled: false }); });
    load();
    // 60s polling — the cache window. No websocket: presence is ambient, not live.
    const t = setInterval(load, 60_000);
    return () => { live = false; clearInterval(t); };
  }, [siteId]);

  // No skeleton, no placeholder: an absent line must never reserve space, or
  // the header would shift on every load.
  if (!data || !data.enabled || !data.count) return null;

  const testers = data.testers ?? [];
  const text =
    `${data.count} deliverable${data.count === 1 ? "" : "s"} in QA` +
    (testers.length ? ` · ${testers.join(", ")}` : "");

  const body = (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
      <FlaskConical size={13} style={{ color: "var(--signal)", flexShrink: 0 }} />
      <span className="ds-text-secondary">{text}</span>
      {data.stale && <span className="ds-text-muted">· last known</span>}
      {data.open_in_qa_url && <ExternalLink size={11} style={{ flexShrink: 0, opacity: 0.6 }} />}
    </span>
  );

  return (
    <div style={{ marginTop: 8, fontSize: "var(--text-caption)" }}>
      {data.open_in_qa_url ? (
        <a href={data.open_in_qa_url} style={{ textDecoration: "none" }}>
          {body}
        </a>
      ) : (
        body
      )}
    </div>
  );
}
