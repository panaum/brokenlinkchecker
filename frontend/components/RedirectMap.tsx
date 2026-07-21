"use client";

import React, { useState, useMemo } from "react";
import { LinkResult, RedirectHop } from "@/types";

function statusColor(status: number): string {
  if (status >= 200 && status < 300) return "var(--signal)";
  if (status >= 300 && status < 400) return "var(--status-attention)";
  return "var(--status-broken)";
}

function shortUrl(u: string): string {
  try {
    const x = new URL(u);
    const path = x.pathname + x.search;
    return x.hostname.replace(/^www\./, "") + (path === "/" ? "" : path);
  } catch {
    return u;
  }
}

// A subway-style route for a redirect chain: each hop is a station whose status
// code sits inside the node; the final destination is the terminus. A URL that
// reappears (a loop) is flagged. Replaces the raw chain; raw text on toggle.
export default function RedirectMap({ result }: { result: LinkResult }) {
  const [raw, setRaw] = useState(false);

  const stations = useMemo(() => {
    const chain: RedirectHop[] = result.redirect_chain ?? [];
    const nodes = chain.map((h) => ({ url: h.url, status: h.status }));
    // Append the final destination as the terminus if it isn't the last hop.
    if (result.final_url && (!nodes.length || nodes[nodes.length - 1].url !== result.final_url)) {
      nodes.push({ url: result.final_url, status: 200 });
    }
    return nodes;
  }, [result]);

  // Loop detection: a URL that appears more than once.
  const seen = new Map<string, number>();
  const loopIndices = new Set<number>();
  stations.forEach((s, i) => {
    if (seen.has(s.url)) loopIndices.add(i);
    else seen.set(s.url, i);
  });
  const hasLoop = loopIndices.size > 0 || (result.redirect_flags?.includes("loop") ?? false);

  if (stations.length < 2) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span className="font-mono ds-text-muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Redirect route · {stations.length - 1} hop{stations.length - 1 === 1 ? "" : "s"}
          {hasLoop && <span style={{ color: "var(--status-broken)" }}> · loop</span>}
        </span>
        <button onClick={() => setRaw((v) => !v)} className="ds-text-muted no-print" style={{ background: "none", border: "none", cursor: "pointer", fontSize: 11, textDecoration: "underline" }}>
          {raw ? "route map" : "raw chain"}
        </button>
      </div>

      {raw ? (
        <div className="font-mono" style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.7 }}>
          {stations.map((s, i) => (
            <div key={i} style={{ wordBreak: "break-all" }}>
              <span style={{ color: statusColor(s.status) }}>{s.status}</span> {s.url}
            </div>
          ))}
        </div>
      ) : (
        <div style={{ display: "flex", alignItems: "flex-start", gap: 0, overflowX: "auto", paddingBottom: 4 }}>
          {stations.map((s, i) => {
            const color = statusColor(s.status);
            const isTerminus = i === stations.length - 1;
            return (
              <React.Fragment key={i}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, minWidth: 64, flexShrink: 0 }}>
                  <div
                    className="font-mono"
                    title={s.url}
                    style={{
                      width: isTerminus ? 40 : 36, height: isTerminus ? 40 : 36, borderRadius: "50%",
                      border: `2px solid ${color}`, color,
                      background: loopIndices.has(i) ? "rgba(224,92,92,0.12)" : "rgba(28,28,46,0.04)",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 12, fontWeight: 700, flexShrink: 0,
                    }}
                  >
                    {s.status}
                  </div>
                  <span className="font-mono ds-text-muted" style={{ fontSize: 10, maxWidth: 76, textAlign: "center", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={s.url}>
                    {shortUrl(s.url)}
                  </span>
                </div>
                {!isTerminus && (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-start", paddingTop: 17, minWidth: 28, flex: "0 1 40px" }}>
                    <div style={{ height: 2, width: "100%", background: "linear-gradient(90deg, var(--border-strong), var(--border-strong))" }} />
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      )}

      {typeof result.response_ms === "number" && result.response_ms > 0 && (
        <span className="font-mono ds-text-muted" style={{ fontSize: 10 }}>
          total {Math.round(result.response_ms)}ms
        </span>
      )}
    </div>
  );
}
