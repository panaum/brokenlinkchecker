"use client";

interface Obs { statement: string; severity: string; first_seen: string | null; resolved_at: string | null; status: string; }
interface RegimeData { sessions_count: number; observations: Obs[]; summary: string; }
export interface AttestationDocData {
  scope_statement: string;
  period: { start: string; end: string; coverage_note: string; prorated: boolean };
  methodology: { cadence: string; engine_version: number; classification_version: number; checks: Record<string, string[]> };
  regimes: Record<string, RegimeData>;
  evidence: Array<{ regime: string; mode: string; at: string; ref_hash: string; requests: number }>;
  coverage: { pages_enrolled: number; site_total_pages: number | null; checks_not_performed: string[]; limitations: string[] };
  signoff: { observing_party: string; issued_at: string; site_url: string };
}

const INK = "#1c1a2e", SECONDARY = "#55506b", MUTED = "#8a86a0", PAPER = "#ffffff", PAGE = "#f4f3f9", LINE = "#e7e4f0", BRAND = "#4f46e5";
const REGIME_LABEL: Record<string, string> = { UK: "United Kingdom — UK GDPR / PECR", US: "United States — CCPA / CPRA" };
const sevWord: Record<string, string> = { critical: "critical", high: "high", medium: "medium" };

export default function AttestationDoc({ doc, contentHash, agency, issuedAt }: { doc: AttestationDocData; contentHash?: string; agency?: string; issuedAt?: string }) {
  const observing = agency || doc.signoff.observing_party;
  const H2: React.CSSProperties = { fontFamily: "var(--font-stack-display)", fontSize: 18, fontWeight: 700, color: INK, marginBottom: 12 };
  return (
    <div className="report-root" style={{ background: PAGE, minHeight: "100vh", padding: "40px 20px", color: INK, fontFamily: "var(--font-stack-body)" }}>
      <article style={{ maxWidth: 820, margin: "0 auto", background: PAPER, borderRadius: 16, boxShadow: "0 10px 40px rgba(28,26,46,0.10)", overflow: "hidden" }}>

        {/* Masthead */}
        <header className="report-masthead" style={{ padding: "38px 48px 26px", borderBottom: `2px solid ${INK}` }}>
          <div style={{ fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase", color: MUTED }}>Data-governance observation attestation</div>
          <h1 style={{ fontFamily: "var(--font-stack-display)", fontSize: 30, fontWeight: 800, letterSpacing: "-0.02em", margin: "8px 0 10px", color: INK }}>
            {doc.signoff.site_url ? doc.signoff.site_url.replace(/^https?:\/\//, "") : "Site"} · {new Date(doc.period.start).toLocaleDateString(undefined, { month: "short", day: "numeric" })}–{new Date(doc.period.end).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
          </h1>
          <div style={{ color: SECONDARY, fontSize: 14 }}>Prepared by <strong style={{ color: INK }}>{observing}</strong> · issued {issuedAt || doc.signoff.issued_at}</div>
        </header>

        {/* Scope statement — the wording law, front and centre */}
        <section className="report-block" style={{ padding: "22px 48px", background: "#f8f6ff", borderBottom: `1px solid ${LINE}` }}>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: MUTED, marginBottom: 6 }}>Scope</div>
          <div style={{ fontSize: 15, color: INK, fontWeight: 500, lineHeight: 1.5 }}>{doc.scope_statement}</div>
        </section>

        {/* Methodology */}
        <section className="report-block" style={{ padding: "26px 48px", borderBottom: `1px solid ${LINE}` }}>
          <h2 style={H2}>Methodology</h2>
          <div style={{ color: SECONDARY, fontSize: 13.5, marginBottom: 10 }}>
            Automated technical observation, {doc.methodology.cadence} cadence · engine v{doc.methodology.engine_version} · classification table v{doc.methodology.classification_version}. {doc.period.coverage_note}
          </div>
          {Object.entries(doc.methodology.checks).map(([regime, checks]) => (
            <div key={regime} style={{ marginTop: 8 }}>
              <div style={{ fontSize: 12.5, fontWeight: 700, color: INK }}>{REGIME_LABEL[regime] || regime}</div>
              <ul style={{ margin: "4px 0 0", paddingLeft: 18, color: SECONDARY, fontSize: 12.5, lineHeight: 1.5 }}>
                {checks.map((ch, i) => <li key={i}>{ch}</li>)}
              </ul>
            </div>
          ))}
        </section>

        {/* Per-regime findings */}
        {Object.entries(doc.regimes).map(([regime, r]) => (
          <section key={regime} className="report-block" style={{ padding: "26px 48px", borderBottom: `1px solid ${LINE}` }}>
            <h2 style={H2}>{REGIME_LABEL[regime] || regime}</h2>
            <div style={{ color: SECONDARY, fontSize: 13.5, marginBottom: r.observations.length ? 14 : 0 }}>{r.summary}</div>
            {r.observations.length > 0 && (
              <div style={{ border: `1px solid ${LINE}`, borderRadius: 8, overflow: "hidden" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 90px 90px 80px", gap: 0, fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.04em", color: MUTED, padding: "8px 12px", background: PAGE }}>
                  <span>Observation</span><span>First seen</span><span>Resolved</span><span>Status</span>
                </div>
                {r.observations.map((o, i) => (
                  <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 90px 90px 80px", gap: 0, alignItems: "center", padding: "9px 12px", borderTop: `1px solid ${LINE}`, fontSize: 12.5 }}>
                    <span style={{ color: INK }}>{o.statement}</span>
                    <span style={{ color: SECONDARY, fontFamily: "var(--font-stack-mono)", fontSize: 11.5 }}>{o.first_seen || "—"}</span>
                    <span style={{ color: SECONDARY, fontFamily: "var(--font-stack-mono)", fontSize: 11.5 }}>{o.resolved_at || "—"}</span>
                    <span style={{ color: o.status === "open" ? "#c0392b" : "#16a34a", fontWeight: 600, fontSize: 11.5 }}>{o.status === "open" ? "Open" : "Resolved"}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        ))}

        {/* Coverage honesty block */}
        <section className="report-block" style={{ padding: "26px 48px", borderBottom: `1px solid ${LINE}`, background: PAGE }}>
          <h2 style={H2}>Coverage &amp; limitations</h2>
          <div style={{ color: SECONDARY, fontSize: 13, lineHeight: 1.6 }}>
            <div>Pages enrolled for observation: <strong style={{ color: INK }}>{doc.coverage.pages_enrolled}</strong>{doc.coverage.site_total_pages != null ? ` of ${doc.coverage.site_total_pages} total` : " (site total not enumerated)"}.</div>
            <div style={{ marginTop: 8, fontWeight: 600, color: INK }}>Checks not performed</div>
            <ul style={{ margin: "3px 0 0", paddingLeft: 18 }}>{doc.coverage.checks_not_performed.map((n, i) => <li key={i}>{n}</li>)}</ul>
            {doc.coverage.limitations.length > 0 && <>
              <div style={{ marginTop: 8, fontWeight: 600, color: INK }}>Declared limitations (verbatim)</div>
              <ul style={{ margin: "3px 0 0", paddingLeft: 18 }}>{doc.coverage.limitations.map((n, i) => <li key={i}>{n}</li>)}</ul>
            </>}
          </div>
        </section>

        {/* Evidence appendix */}
        {doc.evidence.length > 0 && (
          <section className="report-block" style={{ padding: "26px 48px", borderBottom: `1px solid ${LINE}` }}>
            <h2 style={H2}>Evidence appendix</h2>
            <div style={{ color: MUTED, fontSize: 12, marginBottom: 8 }}>Each row references an immutable ledger session by hash.</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              {doc.evidence.slice(0, 16).map((e, i) => (
                <div key={i} style={{ display: "flex", gap: 12, fontSize: 11.5, fontFamily: "var(--font-stack-mono)", color: SECONDARY }}>
                  <span style={{ width: 130 }}>{e.at ? new Date(e.at).toLocaleDateString() : ""}</span>
                  <span style={{ width: 90, color: BRAND }}>{e.regime} · {e.mode}</span>
                  <span style={{ flex: 1 }}>ref {e.ref_hash} · {e.requests} requests</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Sign-off + hash */}
        <footer style={{ padding: "26px 48px", display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 16 }}>
          <div>
            <div style={{ color: MUTED, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em" }}>Observing party</div>
            <div style={{ fontFamily: "var(--font-stack-display)", fontSize: 17, fontWeight: 700, color: INK }}>{observing}</div>
            <div style={{ color: SECONDARY, fontSize: 12, marginTop: 2 }}>Issued {issuedAt || doc.signoff.issued_at}</div>
          </div>
          {contentHash && (
            <div style={{ textAlign: "right" }}>
              <div style={{ color: MUTED, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em" }}>Document hash (immutable)</div>
              <div style={{ fontFamily: "var(--font-stack-mono)", fontSize: 11, color: SECONDARY, wordBreak: "break-all", maxWidth: 300 }}>{contentHash}</div>
            </div>
          )}
        </footer>
      </article>
    </div>
  );
}
