"use client";

import React, { useEffect, useState } from "react";
import { Boxes, ExternalLink } from "lucide-react";

interface Deliverable {
  name: string;
  qa_page_ref: string;
  status: string; // IN_PROGRESS | IN_QA | LIVE
  checklist: { passed: number; failed: number; na: number; total: number };
  qa_score: number | null;
  signed_off_at: string | null;
  open_in_qa_url: string | null;
}
type Data =
  | { deliverables: Deliverable[]; as_of: string; stale?: boolean }
  | { unavailable: true };

function statusChip(status: string): { cls: string; word: string } {
  if (status === "LIVE") return { cls: "ds-status-healthy", word: "Live" };
  if (status === "IN_QA") return { cls: "ds-status-attention", word: "In QA" };
  return { cls: "ds-status-neutral", word: "In progress" };
}

function fmt(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

// The federation's first visible LinkSpy UI: the delivery half of each linked
// site, read from the QA app. Verdict-first, agency (dark) register, staleness
// over errors, designed empty/unavailable states.
export default function DeliveryPanel({ siteId }: { variant?: "dark" | "light"; siteId: string }) {
  const [data, setData] = useState<Data | null>(null);

  useEffect(() => {
    let live = true;
    fetch(`/api/delivery?site_id=${encodeURIComponent(siteId)}`, { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => { if (live) setData(d); })
      .catch(() => { if (live) setData({ unavailable: true }); });
    return () => { live = false; };
  }, [siteId]);

  const Header = ({ children }: { children: React.ReactNode }) => (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
      <Boxes size={18} style={{ color: "var(--signal)", flexShrink: 0 }} />
      <span className="font-display ds-text-primary" style={{ fontWeight: 700, fontSize: "var(--text-heading)" }}>
        Delivery
      </span>
      <span style={{ flex: 1 }} />
      {children}
    </div>
  );

  // Layout-matched skeleton.
  if (data === null) {
    return (
      <div className="ds-card ds-card-pad">
        <Header>{null}</Header>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div className="ds-skeleton" style={{ height: 20, width: "60%" }} />
          <div className="ds-skeleton" style={{ height: 44 }} />
          <div className="ds-skeleton" style={{ height: 44 }} />
        </div>
      </div>
    );
  }

  if ("unavailable" in data) {
    return (
      <div className="ds-card ds-card-pad">
        <Header>{null}</Header>
        <p className="ds-text-secondary" style={{ fontSize: "var(--text-body)" }}>
          The delivery view is unavailable right now. It will appear here once the QA app is reachable.
        </p>
      </div>
    );
  }

  const ds = data.deliverables ?? [];
  if (ds.length === 0) {
    return (
      <div className="ds-card ds-card-pad">
        <Header>{null}</Header>
        <p className="ds-text-secondary" style={{ fontSize: "var(--text-body)" }}>
          No deliverables linked yet — pages linked in the QA app appear here.
        </p>
      </div>
    );
  }

  const signedOff = ds.filter((d) => d.signed_off_at).length;
  const inQa = ds.filter((d) => d.status === "IN_QA").length;

  return (
    <div className="ds-card ds-card-pad">
      <Header>
        {data.stale && (
          <span className="ds-text-muted font-mono" style={{ fontSize: "var(--text-caption)" }}>
            as of {fmt(data.as_of)}
          </span>
        )}
      </Header>

      {/* Verdict-first summary */}
      <div className="ds-text-primary" style={{ fontSize: "var(--text-body)", fontWeight: 600, marginBottom: 14 }}>
        <span className="font-mono">{ds.length}</span> deliverable{ds.length === 1 ? "" : "s"}
        {" · "}
        <span className="font-mono">{signedOff}</span> signed off
        {inQa > 0 && <> · <span className="font-mono">{inQa}</span> in QA</>}
      </div>

      <div style={{ display: "flex", flexDirection: "column" }}>
        {ds.map((d, i) => {
          const chip = statusChip(d.status);
          return (
            <div
              key={d.qa_page_ref}
              style={{
                display: "flex", alignItems: "center", gap: 12, padding: "12px 0", flexWrap: "wrap",
                borderTop: i === 0 ? "none" : "1px solid var(--border-subtle)",
              }}
            >
              <div style={{ minWidth: 0, flex: 1 }}>
                <div className="ds-text-primary" style={{ fontSize: "var(--text-body)", fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {d.name}
                </div>
                {d.signed_off_at && (
                  <div className="ds-text-muted" style={{ fontSize: "var(--text-caption)" }}>Signed off {fmt(d.signed_off_at)}</div>
                )}
              </div>

              <span className={`ds-status ${chip.cls}`} style={{ flexShrink: 0 }}>
                <span className="ds-status-dot" />
                {chip.word}
              </span>

              <span className="ds-text-secondary font-mono" style={{ fontSize: "var(--text-caption)", flexShrink: 0 }} title="Checklist passed / total">
                {d.checklist.passed}/{d.checklist.total}
              </span>

              {d.open_in_qa_url && (
                <a
                  href={d.open_in_qa_url}
                  className="ds-btn-ghost"
                  style={{ display: "inline-flex", alignItems: "center", gap: 6, flexShrink: 0, textDecoration: "none" }}
                >
                  Open in QA <ExternalLink size={13} />
                </a>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
