"use client";

import React, { useState, useEffect, useCallback } from "react";
import { GitPullRequest, ExternalLink } from "lucide-react";

interface Status {
  enabled?: boolean;
  allowlist?: string[];
  error?: string;
}

interface PR {
  branch: string;
  url: string;
  edits: number;
}

interface RunResult {
  refused?: string | boolean | null;
  error?: string;
  note?: string;
  prs?: PR[];
}

interface HistoryEntry {
  repo: string;
  url: string;
  prs: PR[];
}

// Pull "#4" out of a GitHub PR URL for the history line.
function prNumber(url: string): string {
  const m = url.match(/\/pull\/(\d+)/);
  return m ? `#${m[1]}` : "";
}

// Turn a raw backend error into a sentence an operator can act on. A bad token
// surfaces from GitHub as a 401 / "Bad credentials" inside the 500 error string.
function humanizeError(raw: string): string {
  const s = raw.toLowerCase();
  if (s.includes("401") || s.includes("bad credentials") || s.includes("unauthorized")) {
    return "GitHub token invalid or expired — update SELF_HEAL_GITHUB_TOKEN on the server, then try again.";
  }
  if (s.includes("403") || s.includes("forbidden")) {
    return "GitHub refused the token — it may lack permission on this repository. Check the token's repository access.";
  }
  if (s.includes("404") || s.includes("not found")) {
    return "Repository not found for this token — confirm the name and that the token can see it.";
  }
  if (s.includes("no self_heal_github_token")) {
    return "No GitHub token is configured on the server — set SELF_HEAL_GITHUB_TOKEN, then try again.";
  }
  return raw;
}

export default function SelfHealPanel() {
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [repo, setRepo] = useState("");
  const [url, setUrl] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/self-heal/status", { cache: "no-store" });
      const data = await res.json();
      setStatus(data);
      if (data.allowlist?.length) setRepo((r) => r || data.allowlist[0]);
    } catch {
      setStatus({ error: "Could not reach the backend." });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const enabled = Boolean(status?.enabled);
  const allowlist = status?.allowlist ?? [];
  const repoAllowed = allowlist.includes(repo.trim());

  // The Run button is NEVER silently disabled. If it can't run, we say why —
  // right next to the button, in words the operator can act on.
  let blockReason = "";
  if (!enabled) blockReason = "Self-heal is disabled on the server (set SELF_HEAL to enable).";
  else if (!allowlist.length) blockReason = "No approved repositories yet — add one to the allowlist on the server.";
  else if (!repoAllowed) blockReason = "That repository is not approved.";
  else if (!url.trim()) blockReason = "Enter a page URL to scan and fix.";
  const canRun = !blockReason && !running;

  const run = async () => {
    if (!canRun) return;
    setRunning(true);
    setResult(null);
    try {
      const res = await fetch("/api/self-heal/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo: repo.trim(), url: url.trim(), fix_type: "redirect" }),
      });
      const data: RunResult = await res.json();
      setResult(data);
      if (data.prs?.length) {
        setHistory((h) => [{ repo: repo.trim(), url: url.trim(), prs: data.prs! }, ...h]);
      }
    } catch (e) {
      setResult({ error: e instanceof Error ? e.message : "Request failed" });
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return (
      <div className="ds-card ds-card-pad" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="ds-skeleton" style={{ height: 20, width: "40%" }} />
        <div className="ds-skeleton" style={{ height: 44, width: "100%" }} />
        <div className="ds-skeleton" style={{ height: 44, width: "100%" }} />
      </div>
    );
  }

  const prs = result?.prs ?? [];
  const refused = result?.refused && result.refused !== null;

  return (
    <div className="ds-card ds-card-pad" style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
      {/* State chip — no weapons language. */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <span
          className={`ds-status ${enabled ? "ds-status-healthy" : "ds-status-neutral"}`}
          style={{ padding: "5px 12px", borderRadius: "var(--radius-pill)", background: enabled ? "var(--status-healthy-bg)" : "var(--status-neutral-bg)" }}
        >
          <span className="ds-status-dot" />
          {enabled ? "Active · opens PRs only, never merges" : "Disabled"}
        </span>
        <a
          href="/dashboard"
          className="ds-text-secondary"
          style={{ fontSize: "var(--text-caption)", textDecoration: "none" }}
        >
          Manage approved repositories →
        </a>
      </div>

      {/* Persistent PR hero — after a run, the thing to review lives here. */}
      {prs.length > 0 && (
        <div
          style={{
            background: "var(--status-healthy-bg)",
            border: "1px solid rgba(76,175,125,0.28)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-4)",
          }}
        >
          <div className="ds-text-primary" style={{ fontSize: "var(--text-heading)", fontWeight: 600, marginBottom: 4 }}>
            {prs.length === 1 ? "1 pull request opened" : `${prs.length} pull requests opened`}
          </div>
          <div className="ds-text-secondary" style={{ fontSize: "var(--text-body)", marginBottom: 12 }}>
            Review before merging — self-heal never merges for you.
          </div>
          {prs.map((pr) => (
            <a
              key={pr.branch}
              href={pr.url}
              target="_blank"
              rel="noopener noreferrer"
              className="ds-btn-primary"
              style={{ display: "inline-flex", alignItems: "center", gap: 8, textDecoration: "none", marginRight: 8 }}
            >
              <GitPullRequest size={15} />
              Review PR {prNumber(pr.url)} — {pr.edits} {pr.edits === 1 ? "fix" : "fixes"}
            </a>
          ))}
        </div>
      )}

      {/* Inputs */}
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
        <label className="ds-text-secondary" style={{ fontSize: "var(--text-caption)" }}>
          Repository
        </label>
        {allowlist.length > 0 ? (
          <select
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
            style={{
              background: "var(--surface-raised)", border: "1px solid var(--border-subtle)",
              color: "var(--text-primary)", borderRadius: "var(--radius-md)", padding: "10px 12px",
              fontSize: "var(--text-body)",
            }}
          >
            {allowlist.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        ) : (
          <div className="ds-text-muted" style={{ fontSize: "var(--text-body)", padding: "10px 12px", background: "var(--surface-raised)", borderRadius: "var(--radius-md)", border: "1px solid var(--border-subtle)" }}>
            No approved repositories configured.
          </div>
        )}

        <label className="ds-text-secondary" style={{ fontSize: "var(--text-caption)", marginTop: 8 }}>
          Page URL to scan and fix
        </label>
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }}
          placeholder="https://example.com/landing"
          style={{
            background: "var(--surface-raised)", border: "1px solid var(--border-subtle)",
            color: "var(--text-primary)", borderRadius: "var(--radius-md)", padding: "10px 12px",
            fontSize: "var(--text-body)", outline: "none",
          }}
        />
      </div>

      {/* Run — never silently disabled; the reason is always visible. */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <button className="ds-btn-primary" onClick={run} disabled={!canRun}>
          {running ? "Scanning and fixing…" : "Run self-heal"}
        </button>
        {blockReason && (
          <span className="ds-text-muted" style={{ fontSize: "var(--text-caption)" }}>
            {blockReason}
          </span>
        )}
      </div>

      {/* Non-PR outcomes: refusal / plain-language error / nothing-provable. */}
      {result && prs.length === 0 && (
        <div style={{ fontSize: "var(--text-body)" }}>
          {refused ? (
            <span className="ds-status ds-status-neutral"><span className="ds-status-dot" />{String(result.refused)}</span>
          ) : result.error ? (
            <span className="ds-status ds-status-broken"><span className="ds-status-dot" />{humanizeError(result.error)}</span>
          ) : (
            <span className="ds-text-secondary">
              {result.note || "Nothing provable to fix on that page — no PR opened."}
            </span>
          )}
        </div>
      )}

      {/* Run history — this session's runs that opened PRs. */}
      {history.length > 0 && (
        <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "var(--space-4)" }}>
          <div className="ds-text-muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
            Run history
          </div>
          {history.flatMap((h) =>
            h.prs.map((pr) => (
              <div key={pr.branch} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "6px 0", fontSize: "var(--text-body)" }}>
                <span className="ds-text-secondary">
                  Opened PR {prNumber(pr.url)} — {pr.edits} redirect {pr.edits === 1 ? "fix" : "fixes"} on {h.repo}
                </span>
                <a href={pr.url} target="_blank" rel="noopener noreferrer" className="ds-text-secondary" style={{ display: "inline-flex", alignItems: "center", gap: 4, textDecoration: "none", flexShrink: 0 }}>
                  View on GitHub <ExternalLink size={12} />
                </a>
              </div>
            )),
          )}
        </div>
      )}
    </div>
  );
}
