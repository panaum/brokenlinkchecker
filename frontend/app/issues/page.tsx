"use client";

/*
 * Phase 3 — issue results UI (three-column), mocked data, no backend wiring.
 * Ported from linkspy-issue-primitive.html's "After re-scan" view. Styling +
 * token vars live in ./issues.css (mirrors @qa/tokens until the package is
 * build-wired). Viewable at /issues.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Inter, JetBrains_Mono } from "next/font/google";
import { BlockedState, FirstRunState, EmptyState, ClientReport } from "./states";
import "./issues.css";

const inter = Inter({ subsets: ["latin"], weight: ["400", "500", "600", "700", "800"] });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500"] });

// ─── Types + mocked data ─────────────────────────────────────────────────────
type Status = "open" | "fixed" | "ignored";
export type Issue = {
  id: string;
  target: string;
  tag: string;
  tagCls: "bad" | "ok" | "warn" | "neutral";
  severity: string;            // HIGH TRAFFIC | LOW TRAFFIC | RESOLVED
  band: "high" | "low";        // traffic band for grouping
  region: string;
  pageviews: number;
  scans: number;
  status: Status;
  anchorText: string;
  builder: string;
  scoreImpact: string;
  linkType: "internal" | "external" | "anchor";
  domain: string;
  summary: string;
  clientFix: string;
  occurrences: { region: string; label: string; severity: "high" | "med" | "low" }[];
  life: { date: string; label: string; status: "done" | "now" }[];
};

const SCORE = 91;
const CIRC = 2 * Math.PI * 32; // 201.06

const ISSUES: Issue[] = [
  {
    id: "1", target: "/book-now", tag: "404", tagCls: "bad", severity: "HIGH TRAFFIC",
    band: "high", region: "nav", pageviews: 1240, scans: 4, status: "open",
    anchorText: "Book now", builder: "Elementor", scoreImpact: "−6",
    linkType: "internal", domain: "smilelabny",
    summary: "Linked from three places and every one returns 404. Both the nav and hero instances sit above the fold on a page taking roughly 1,240 visits a month.",
    clientFix: "The “Book now” button in your main menu leads to a missing page — it needs to point to /book-online.",
    occurrences: [
      { region: "Nav", label: "Primary menu, item 4", severity: "high" },
      { region: "Hero", label: "Sticky CTA button", severity: "high" },
      { region: "Footer", label: "Quick links column", severity: "low" },
    ],
    life: [
      { date: "11 Jul", label: "last ok", status: "done" },
      { date: "14 Jul", label: "detected", status: "done" },
      { date: "18 Jul", label: "still open", status: "done" },
      { date: "22 Jul", label: "still open", status: "now" },
    ],
  },
  {
    id: "2", target: "hero button", tag: "Dead", tagCls: "warn", severity: "HIGH TRAFFIC",
    band: "high", region: "hero", pageviews: 1240, scans: 2, status: "open",
    anchorText: "Schedule today", builder: "Elementor", scoreImpact: "−2",
    linkType: "internal", domain: "smilelabny",
    summary: "The button renders and looks clickable but has no destination set. It is the first call to action a visitor sees.",
    clientFix: "The “Schedule today” button at the top of your homepage doesn’t go anywhere when clicked — it needs a destination link.",
    occurrences: [{ region: "Hero", label: "Above the fold CTA", severity: "high" }],
    life: [
      { date: "18 Jul", label: "last ok", status: "done" },
      { date: "20 Jul", label: "detected", status: "done" },
      { date: "22 Jul", label: "still open", status: "now" },
    ],
  },
  {
    id: "3", target: "/team/dr-lewis", tag: "404", tagCls: "bad", severity: "LOW TRAFFIC",
    band: "low", region: "footer", pageviews: 60, scans: 3, status: "open",
    anchorText: "Dr. Lewis", builder: "Elementor", scoreImpact: "−1",
    linkType: "internal", domain: "smilelabny",
    summary: "Staff page was removed but the footer link stayed behind. Low traffic, so it is ranked below the two above.",
    clientFix: "The “Dr. Lewis” link in your footer points to a page that no longer exists — remove it or point it to the team page.",
    occurrences: [{ region: "Footer", label: "Meet the team column", severity: "low" }],
    life: [
      { date: "14 Jul", label: "last ok", status: "done" },
      { date: "16 Jul", label: "detected", status: "done" },
      { date: "22 Jul", label: "still open", status: "now" },
    ],
  },
  {
    id: "4", target: "/services/implants", tag: "Fixed", tagCls: "ok", severity: "RESOLVED",
    band: "high", region: "nav", pageviews: 1240, scans: 2, status: "fixed",
    anchorText: "Implants", builder: "Elementor", scoreImpact: "0",
    linkType: "internal", domain: "smilelabny",
    summary: "Verified fixed by this re-scan. The page now returns 200 from all locations it is linked from.",
    clientFix: "",
    occurrences: [
      { region: "Nav", label: "Services dropdown", severity: "low" },
      { region: "Body", label: "Treatment grid", severity: "low" },
    ],
    life: [
      { date: "20 Jul", label: "detected", status: "done" },
      { date: "22 Jul", label: "fixed", status: "now" },
    ],
  },
  {
    id: "5", target: "/pages/new-patients", tag: "Fixed", tagCls: "ok", severity: "RESOLVED",
    band: "low", region: "footer", pageviews: 310, scans: 1, status: "fixed",
    anchorText: "New patients", builder: "Elementor", scoreImpact: "0",
    linkType: "internal", domain: "smilelabny",
    summary: "Verified fixed by this re-scan. A redirect was added on the CMS side.",
    clientFix: "",
    occurrences: [{ region: "Footer", label: "Quick links column", severity: "low" }],
    life: [
      { date: "20 Jul", label: "detected", status: "done" },
      { date: "22 Jul", label: "fixed", status: "now" },
    ],
  },
];

type Filter = { dim: string; value: string; label: string };

const AGE_ROWS = [
  { value: "this", label: "This scan", count: 1, w: 20 },
  { value: "2-3", label: "2–3 scans", count: 2, w: 40 },
  { value: "4+", label: "4+ scans", count: 1, w: 20 },
];
const LINKTYPE_ROWS = [
  { value: "internal", label: "Internal", count: 111, w: 78 },
  { value: "external", label: "External", count: 21, w: 15 },
  { value: "anchor", label: "Anchor", count: 8, w: 6 },
];
const DOMAIN_ROWS = [
  { value: "smilelabny", label: "smilelabny", count: 111, w: 78 },
  { value: "nexhealth", label: "nexhealth", count: 12, w: 9 },
];

const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const pct = (n: number, total: number) => (total ? Math.round((n / total) * 100) : 0);

function deriveDomains(issues: Issue[]) {
  const counts: Record<string, number> = {};
  for (const i of issues) counts[i.domain] = (counts[i.domain] || 0) + 1;
  const total = issues.length;
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1]).slice(0, 3)
    .map(([value, count]) => ({ value, label: value, count, w: pct(count, total) }));
}

// Live data passed in from the real scanner; when omitted, the mocked demo data
// is used (so /issues and /scanner keep working).
export type ResultsData = {
  siteName: string; totalLinks: number; healthy: number; broken: number;
  deadCta: number; score: number; issues: Issue[];
};

// The three-column results UI as a standalone, embeddable component (used by
// /issues with a demo switcher, /scanner under the scan form, and the live /).
export function ResultsView({ data }: { data?: ResultsData } = {}) {
  const issuesData = data ? data.issues : ISSUES;
  const targetScore = data ? data.score : SCORE;
  const siteName = data ? data.siteName : "smilelabny.com";
  const totalLinks = data ? data.totalLinks : 142;
  const healthyN = data ? data.healthy : 139;
  const brokenN = data ? data.broken : 2;
  const deadN = data ? data.deadCta : 1;
  const byTraffic = issuesData.some((i) => i.pageviews > 0);
  const [statuses, setStatuses] = useState<Record<string, Status>>({});
  const [view, setView] = useState<Status>("open");
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [selectedId, setSelectedId] = useState("1");
  const [filter, setFilter] = useState<Filter | null>(null);
  const [ringOpen, setRingOpen] = useState(false);
  const [score, setScore] = useState(0);
  const [barsIn, setBarsIn] = useState(false);
  const [copied, setCopied] = useState(false);
  const [toast, setToast] = useState<{ id: string; prev: Status } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const statusOf = useCallback(
    (iss: Issue) => statuses[iss.id] ?? iss.status,
    [statuses],
  );

  // debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim().toLowerCase()), 180);
    return () => clearTimeout(t);
  }, [query]);

  // score ring count-up + bar reveal on mount
  useEffect(() => {
    setBarsIn(true);
    if (prefersReducedMotion()) { setScore(targetScore); return; }
    let raf = 0;
    let start = 0;
    const tick = (ts: number) => {
      if (!start) start = ts;
      const p = Math.min((ts - start) / 1100, 1);
      setScore(Math.round(targetScore * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [targetScore]);

  const matches = useCallback(
    (iss: Issue) => {
      if (debounced &&
        !iss.target.toLowerCase().includes(debounced) &&
        !iss.anchorText.toLowerCase().includes(debounced)) return false;
      if (!filter) return true;
      switch (filter.dim) {
        case "health": return iss.tagCls === filter.value;
        case "age": {
          if (filter.value === "this") return iss.scans <= 1;
          if (filter.value === "2-3") return iss.scans >= 2 && iss.scans <= 3;
          return iss.scans >= 4;
        }
        case "linktype": return iss.linkType === filter.value;
        case "domain": return iss.domain === filter.value;
        default: return true;
      }
    },
    [debounced, filter],
  );

  const openIssues = issuesData.filter((i) => statusOf(i) === "open" && matches(i));
  const fixedIssues = issuesData.filter((i) => statusOf(i) === "fixed" && matches(i));
  const ignoredIssues = issuesData.filter((i) => statusOf(i) === "ignored" && matches(i));

  const counts = {
    open: issuesData.filter((i) => statusOf(i) === "open").length,
    fixed: issuesData.filter((i) => statusOf(i) === "fixed").length,
    ignored: issuesData.filter((i) => statusOf(i) === "ignored").length,
  };

  // display order (also drives J/K + "N of M")
  const groups = useMemo(() => {
    if (view === "open") {
      const g: { key: string; label: string; sev: "hi" | "lo" | "ok"; items: Issue[] }[] = [];
      const high = openIssues.filter((i) => i.band === "high");
      const low = openIssues.filter((i) => i.band === "low");
      if (high.length) g.push({ key: "high", label: byTraffic ? "HIGH TRAFFIC · ACT FIRST" : "CRITICAL · ACT FIRST", sev: "hi", items: high });
      if (low.length) g.push({ key: "low", label: byTraffic ? "LOW TRAFFIC" : "LOWER PRIORITY", sev: "lo", items: low });
      if (fixedIssues.length) g.push({ key: "fixed", label: "FIXED THIS SCAN", sev: "ok", items: fixedIssues });
      return g;
    }
    if (view === "fixed") return fixedIssues.length ? [{ key: "fixed", label: "FIXED", sev: "ok" as const, items: fixedIssues }] : [];
    return ignoredIssues.length ? [{ key: "ignored", label: "IGNORED", sev: "lo" as const, items: ignoredIssues }] : [];
  }, [view, openIssues, fixedIssues, ignoredIssues, byTraffic]);

  const order = useMemo(() => groups.flatMap((g) => g.items), [groups]);

  // keep selection valid
  useEffect(() => {
    if (order.length && !order.some((i) => i.id === selectedId)) {
      setSelectedId(order[0].id);
    }
  }, [order, selectedId]);

  const selected = issuesData.find((i) => i.id === selectedId) ?? issuesData[0];
  const selIndex = order.findIndex((i) => i.id === selectedId);

  const step = useCallback(
    (dir: number) => {
      if (!order.length) return;
      const i = selIndex < 0 ? 0 : selIndex;
      const next = Math.min(Math.max(i + dir, 0), order.length - 1);
      setSelectedId(order[next].id);
      setCopied(false);
    },
    [order, selIndex],
  );

  const ignoreCurrent = useCallback(() => {
    const cur = order[selIndex] ?? order[0];
    if (!cur || statusOf(cur) !== "open") return;
    const prev = statusOf(cur);
    // advance selection before it leaves the open list
    const rest = order.filter((i) => i.id !== cur.id);
    const nextSel = rest[Math.min(selIndex, rest.length - 1)]?.id;
    setStatuses((s) => ({ ...s, [cur.id]: "ignored" }));
    if (nextSel) setSelectedId(nextSel);
    setToast({ id: cur.id, prev });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 5000);
  }, [order, selIndex, statusOf]);

  const undo = useCallback(() => {
    if (!toast) return;
    setStatuses((s) => { const n = { ...s }; delete n[toast.id]; return n; });
    setSelectedId(toast.id);
    setToast(null);
    if (toastTimer.current) clearTimeout(toastTimer.current);
  }, [toast]);

  // keyboard: J/K + arrows navigate, E ignores. Skip when typing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); step(1); }
      else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); step(-1); }
      else if (e.key === "e" || e.key === "E") { e.preventDefault(); ignoreCurrent(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step, ignoreCurrent]);

  const toggleFilter = (f: Filter) =>
    setFilter((cur) => (cur && cur.dim === f.dim && cur.value === f.value ? null : f));

  const copyFix = async () => {
    try { await navigator.clipboard.writeText(selected.clientFix || selected.summary); } catch { /* noop */ }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  const isFixed = statusOf(selected) === "fixed";
  const sevBadgeStyle = isFixed
    ? { background: "var(--green-bg)", color: "var(--green)" }
    : selected.severity === "LOW TRAFFIC"
      ? { background: "#F3F2F8", color: "var(--ink-3)" }
      : { background: "var(--red-bg)", color: "var(--red)" };

  const dashoffset = CIRC * (1 - targetScore / 100);

  // Rail cards: derived from live issues, or the mock rows for the demo.
  const ageRows = data
    ? [{ value: "this", label: "This scan", count: issuesData.length, w: 100 }]
    : AGE_ROWS;
  const linktypeRows = data
    ? (["internal", "external", "anchor"] as const).map((v) => {
        const count = issuesData.filter((i) => i.linkType === v).length;
        return { value: v, label: v[0].toUpperCase() + v.slice(1), count, w: pct(count, issuesData.length) };
      }).filter((r) => r.count > 0)
    : LINKTYPE_ROWS;
  const domainRows = data ? deriveDomains(issuesData) : DOMAIN_ROWS;

  return (
    <>
      {/* ── verification banner (mock demo only; real scans have no history yet) ── */}
        {!data && (
        <div className="verify" role="status">
          <div className="verify-icon" aria-hidden>✓</div>
          <div className="grow">
            <h3>You fixed 2 of 4 since 20 July</h3>
            <p>Re-scan verified both. Two issues are still open and one is newly detected.</p>
          </div>
          <div className="verify-list">
            <span className="vchip mono">/services/implants</span>
            <span className="vchip mono">/pages/new-patients</span>
          </div>
        </div>
        )}

        {/* ── banner ── */}
        <div className="banner">
          <div className="banner-top">
            <button
              className="gauge"
              aria-expanded={ringOpen}
              aria-controls="score-breakdown"
              title="How is this calculated?"
              onClick={() => setRingOpen((o) => !o)}
            >
              <svg width="76" height="76" viewBox="0 0 76 76" aria-hidden>
                <defs>
                  <linearGradient id="gg" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor="#7C74F0" />
                    <stop offset="100%" stopColor="#3D2FBF" />
                  </linearGradient>
                </defs>
                <circle className="gauge-track" cx="38" cy="38" r="32" fill="none" strokeWidth="6" />
                <circle
                  className="gauge-val" cx="38" cy="38" r="32" fill="none" strokeWidth="6"
                  strokeDasharray={CIRC} strokeDashoffset={dashoffset}
                />
              </svg>
              <span className="gauge-num mono">{score}</span>
              <span className="gauge-cap">HEALTH</span>
            </button>
            <div className="grow">
              <h2 className="mono">{siteName}</h2>
              <div className="banner-meta">
                <span>{totalLinks.toLocaleString()} links · single page</span><span>·</span><span>scanned just now</span>
                {!data && <span className="delta up">▲ 9 since 20 July</span>}
              </div>
            </div>
            <div className="head-actions">
              <button className="btn-sec">Share report</button>
              <button className="btn-primary">Re-scan</button>
            </div>
          </div>

          {/* health bar — flat, each segment filters */}
          <div className="health-bar">
            <button className="hseg ok" style={{ flex: healthyN || 1 }} aria-pressed={filter?.dim === "health" && filter.value === "ok"}
              aria-label={`${healthyN} healthy links`} onClick={() => toggleFilter({ dim: "health", value: "ok", label: "Healthy links" })} />
            <button className="hseg bad" style={{ flex: brokenN, minWidth: brokenN ? 20 : 0 }} aria-pressed={filter?.dim === "health" && filter.value === "bad"}
              aria-label={`${brokenN} broken links`} onClick={() => toggleFilter({ dim: "health", value: "bad", label: "Broken" })} />
            <button className="hseg warn" style={{ flex: deadN, minWidth: deadN ? 14 : 0 }} aria-pressed={filter?.dim === "health" && filter.value === "warn"}
              aria-label={`${deadN} dead CTA`} onClick={() => toggleFilter({ dim: "health", value: "warn", label: "Dead CTA" })} />
          </div>
          <div className="health-key">
            <span className="key"><i className="ok" />Healthy <b>{healthyN}</b></span>
            <span className="key"><i className="bad" />Broken <b>{brokenN}</b></span>
            <span className="key"><i className="warn" />Dead CTA <b>{deadN}</b></span>
            {!data && <span className="key" style={{ marginLeft: "auto", color: "var(--ink-3)" }}>Click the ring to see how {SCORE} is calculated</span>}
          </div>

          {!data && (
          <div id="score-breakdown" className={`breakdown ${ringOpen ? "open" : ""}`}>
            <div className="breakdown-in">
              <div className="bd-title">HOW {SCORE} IS CALCULATED</div>
              <div className="bd-row"><span className="w">Baseline</span><span className="lbl">All links resolving</span><span className="pts">100</span></div>
              <div className="bd-row"><span className="w">×3 weight</span><span className="lbl">Broken in nav or hero · 1 issue · 1,240 views/mo</span><span className="pts minus">−6</span></div>
              <div className="bd-row"><span className="w">×3 weight</span><span className="lbl">Dead CTA above the fold · 1 issue · 1,240 views/mo</span><span className="pts minus">−2</span></div>
              <div className="bd-row"><span className="w">×1 weight</span><span className="lbl">Broken in footer · 1 issue · 60 views/mo</span><span className="pts minus">−1</span></div>
              <div className="bd-total"><span>Health score</span><span className="mono">{SCORE}</span></div>
              <p className="bd-note">Deductions scale with monthly pageviews from the connected GA4 property, so a broken link on a page nobody visits costs less than one on the money page.</p>
            </div>
          </div>
          )}
        </div>

        {/* ── toolbar ── */}
        <div className="toolbar">
          <input className="field" type="search" placeholder="Filter issues…" aria-label="Filter issues"
            value={query} onChange={(e) => setQuery(e.target.value)} />
          <div className="seg" role="group" aria-label="Issue status">
            {(["open", "fixed", "ignored"] as Status[]).map((v) => (
              <button key={v} aria-pressed={view === v} onClick={() => setView(v)}>
                {v[0].toUpperCase() + v.slice(1)}<b>{counts[v]}</b>
              </button>
            ))}
          </div>
          {filter && (
            <span className="filter-chip">
              {filter.label}
              <button aria-label="Clear filter" onClick={() => setFilter(null)}>×</button>
            </span>
          )}
          <span className="tool-kbd"><kbd>J</kbd><kbd>K</kbd> move <kbd>E</kbd> ignore</span>
        </div>

        {/* ── three columns ── */}
        <div className="grid3">
          {/* issue list */}
          <div className="panel" style={{ boxShadow: "var(--shadow-flat)" }}>
            {groups.length === 0 && (
              <div className="list-foot" style={{ borderTop: 0 }}>No issues match this filter.</div>
            )}
            {groups.map((g) => (
              <div key={g.key}>
                <div className="group-head" style={g.sev === "ok" ? { color: "var(--green)" } : undefined}>
                  <span
                    className={`sev ${g.sev === "ok" ? "" : g.sev}`}
                    style={g.sev === "ok" ? { background: "var(--green)" } : undefined}
                  />
                  {g.label}<span className="n">{g.items.length}</span>
                </div>
                {g.items.map((iss) => {
                  const st = statusOf(iss);
                  return (
                    <button
                      key={iss.id}
                      className={`issue ${st === "fixed" ? "fixed" : ""}`}
                      aria-current={iss.id === selectedId ? "true" : undefined}
                      onClick={() => { setSelectedId(iss.id); setCopied(false); }}
                    >
                      <span className={`tag ${iss.tagCls}`}>{iss.tag}</span>
                      <span className="issue-main">
                        <span className="issue-t mono">{iss.target}</span>
                        <span className="issue-s">
                          {st === "fixed" ? (
                            <>verified just now · was open {iss.scans} scan{iss.scans !== 1 ? "s" : ""}</>
                          ) : (
                            <>
                              {iss.pageviews > 0 && (
                                <><span className="traffic"><i />{iss.pageviews.toLocaleString()}/mo</span> · </>
                              )}
                              {iss.occurrences.map((o) => o.region.toLowerCase()).join(", ")}
                              · <span className="age">open {iss.scans} scan{iss.scans !== 1 ? "s" : ""}</span>
                            </>
                          )}
                        </span>
                      </span>
                      <svg className="issue-chev" width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden>
                        <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </button>
                  );
                })}
              </div>
            ))}
            <div className="list-foot">{healthyN.toLocaleString()} healthy links hidden<button>Show all</button></div>
          </div>

          {/* detail (raised) */}
          <div className="sticky">
            <div className="panel detail-panel">
              <div className="detail-bar">
                <button className="nav-btn" aria-label="Previous issue" disabled={selIndex <= 0} onClick={() => step(-1)}>↑</button>
                <button className="nav-btn" aria-label="Next issue" disabled={selIndex >= order.length - 1} onClick={() => step(1)}>↓</button>
                <span className="pos">{order.length ? selIndex + 1 : 0} of {order.length}</span>
                <span className="sev-badge" style={sevBadgeStyle}>{isFixed ? "RESOLVED" : selected.severity}</span>
              </div>
              <div className="detail" key={selectedId}>
                <div className="detail-top">
                  <h3 className="mono">{selected.target}</h3>
                  <span className={`tag ${selected.tagCls}`} style={{ marginLeft: "auto" }}>{selected.tag}</span>
                </div>
                <div className="sub">{selected.summary}</div>
                <dl className="dl">
                  <dt>Anchor text</dt><dd>{selected.anchorText}</dd>
                  <dt>Monthly views</dt><dd className="mono">{selected.pageviews.toLocaleString()}</dd>
                  <dt>Builder</dt><dd>{selected.builder}</dd>
                  <dt>Score impact</dt><dd className="mono">{selected.scoreImpact} points</dd>
                </dl>

                <div className="sec">
                  <h4>LIFECYCLE</h4>
                  <div className="life">
                    {selected.life.map((l, i) => (
                      <div key={i} className={`life-node ${l.status}`}>
                        <i />
                        <div className="life-d">{l.date}</div>
                        <div className="life-l">{l.label}</div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="sec">
                  <h4>WHERE IT APPEARS</h4>
                  {selected.occurrences.map((o, i) => (
                    <div key={i} className="occ-row">
                      <span className="tag neutral">{o.region}</span>
                      <span>{o.label}</span>
                      <em className={o.severity}>{o.severity}</em>
                    </div>
                  ))}
                </div>

                <div className="detail-actions">
                  {isFixed ? (
                    <>
                      <button className="btn-sec">Open live page</button>
                      <span className="spacer" />
                      <button className="btn-sec">Reopen</button>
                    </>
                  ) : (
                    <>
                      <button className="btn-primary" onClick={copyFix}>{copied ? "Copied ✓" : "Copy fix for client"}</button>
                      <button className="btn-sec">Open live page</button>
                      <span className="spacer" />
                      <button className="btn-sec" onClick={ignoreCurrent}>Ignore</button>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* stats rail */}
          <div className="sticky rail-stack stack">
            <RailCard title="ISSUE AGE" dim="age" rows={ageRows} barsIn={barsIn} filter={filter} onFilter={toggleFilter} />
            <RailCard title="LINK TYPES" dim="linktype" rows={linktypeRows} barsIn={barsIn} filter={filter} onFilter={toggleFilter} />
            <RailCard title="TOP DOMAINS" dim="domain" rows={domainRows} barsIn={barsIn} filter={filter} onFilter={toggleFilter} mono />
          </div>
        </div>

      {/* undo toast */}
      <div className={`toast ${toast ? "show" : ""}`} role="status" aria-live="polite">
        {toast && <>Issue ignored<button onClick={undo}>Undo</button></>}
      </div>
    </>
  );
}

// ─── /issues demo page: the switcher chrome around ResultsView + the states ──
export default function IssuesPage() {
  const [demoView, setDemoView] = useState<"results" | "report" | "blocked" | "firstrun" | "empty">("results");
  return (
    <div
      className={`issues-page ${inter.className}`}
      style={{ "--font-ui": inter.style.fontFamily, "--font-mono": mono.style.fontFamily } as React.CSSProperties}
    >
      <div className="issues-wrap">
        <div className="switcher" role="group" aria-label="Demo view">
          <em>Demo view</em>
          {([
            ["results", "After re-scan"],
            ["report", "Client report"],
            ["blocked", "Scan blocked"],
            ["firstrun", "First run"],
            ["empty", "Empty results"],
          ] as const).map(([v, label]) => (
            <button key={v} className="sw" aria-pressed={demoView === v} onClick={() => setDemoView(v)}>
              {label}
            </button>
          ))}
        </div>

        {demoView === "report" && <ClientReport />}
        {demoView === "blocked" && <BlockedState />}
        {demoView === "firstrun" && <FirstRunState />}
        {demoView === "empty" && <EmptyState />}
        {demoView === "results" && <ResultsView />}
      </div>
    </div>
  );
}

function RailCard({
  title, dim, rows, barsIn, filter, onFilter, mono,
}: {
  title: string; dim: string;
  rows: { value: string; label: string; count: number; w: number }[];
  barsIn: boolean; filter: Filter | null; onFilter: (f: Filter) => void; mono?: boolean;
}) {
  return (
    <div className="panel rail-card" style={{ boxShadow: "var(--shadow-flat)" }}>
      <h3>{title}</h3>
      {rows.map((r) => {
        const active = filter?.dim === dim && filter.value === r.value;
        return (
          <button key={r.value} className="bar-row" aria-pressed={active}
            onClick={() => onFilter({ dim, value: r.value, label: `${title[0] + title.slice(1).toLowerCase()}: ${r.label}` })}>
            <span className={`bar-label ${mono ? "mono" : ""}`}>{r.label}</span>
            <span className="bar"><i style={{ width: barsIn ? `${r.w}%` : 0 }} /></span>
            <span className="bar-val mono">{r.count}</span>
          </button>
        );
      })}
    </div>
  );
}
