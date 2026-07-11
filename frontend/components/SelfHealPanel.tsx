"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Loader2, GitPullRequest, Wrench, ShieldAlert, CheckCircle2 } from "lucide-react";

interface Status {
  enabled?: boolean;
  allowlist?: string[];
  error?: string;
}

interface RunResult {
  refused?: string | boolean | null;
  error?: string;
  note?: string;
  prs?: { branch: string; url: string; edits: number }[];
}

export default function SelfHealPanel() {
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [repo, setRepo] = useState("");
  const [url, setUrl] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/self-heal/status", { cache: "no-store" });
      const data = await res.json();
      setStatus(data);
      // Pre-fill with the first allowlisted repo, if any — nothing else can run.
      if (data.allowlist?.length && !repo) setRepo(data.allowlist[0]);
    } catch {
      setStatus({ error: "Could not reach the backend." });
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const run = async () => {
    setRunning(true);
    setResult(null);
    try {
      const res = await fetch("/api/self-heal/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo: repo.trim(), url: url.trim(), fix_type: "redirect" }),
      });
      setResult(await res.json());
    } catch (e) {
      setResult({ error: e instanceof Error ? e.message : "Request failed" });
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm" style={{ color: "rgba(255,255,255,0.4)" }}>
        <Loader2 size={14} className="animate-spin" /> Loading self-heal…
      </div>
    );
  }

  const enabled = Boolean(status?.enabled);
  const allowlist = status?.allowlist ?? [];
  const repoAllowed = allowlist.includes(repo.trim());
  const prs = result?.prs ?? [];
  const refused = result?.refused && result.refused !== null;

  return (
    <div
      className="rounded-xl p-4"
      style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(147,51,234,0.25)" }}
    >
      <div className="flex items-center gap-2 mb-2" style={{ fontWeight: 600, fontSize: 14 }}>
        <Wrench size={16} style={{ color: "#a855f7" }} />
        Self-heal — auto-fix broken links via pull request
        <span
          style={{
            marginLeft: 6, fontSize: 10, padding: "1px 7px", borderRadius: 999,
            background: enabled ? "rgba(168,85,247,0.15)" : "rgba(255,255,255,0.06)",
            color: enabled ? "#c084fc" : "rgba(255,255,255,0.5)",
          }}
        >
          {enabled ? "armed" : "off"}
        </span>
      </div>

      <p style={{ fontSize: 12, color: "rgba(255,255,255,0.55)", lineHeight: 1.5, marginBottom: 12 }}>
        Scans the page, and for links it can <strong>prove</strong> a fix for (a
        permanent redirect, an insecure asset), opens a pull request. It never
        merges, and never touches a repo that is not on the operator allowlist.
      </p>

      {!enabled && (
        <div
          className="flex gap-2 rounded-lg px-3 py-2 mb-3"
          style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)" }}
        >
          <ShieldAlert size={14} style={{ color: "rgba(255,255,255,0.5)", flexShrink: 0, marginTop: 2 }} />
          <p style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", margin: 0, lineHeight: 1.5 }}>
            Self-heal is off. It stays inert until an operator sets{" "}
            <code>SELF_HEAL</code> on the server. You can still fill in a run below —
            it will report the refusal rather than doing anything.
          </p>
        </div>
      )}

      <div className="flex flex-col gap-2">
        <label style={{ fontSize: 11, color: "rgba(255,255,255,0.4)" }}>
          Repository (owner/name — must be on the allowlist)
        </label>
        <input
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          placeholder="panaum/linkspy-selfheal-test"
          className="rounded-lg px-3 py-2 text-sm outline-none"
          style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: "#fff" }}
        />
        {repo.trim() && !repoAllowed && (
          <span style={{ fontSize: 11, color: "#fca5a5" }}>
            Not on the allowlist{allowlist.length ? ` (${allowlist.join(", ")})` : ""} — a run will be refused.
          </span>
        )}

        <label style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", marginTop: 4 }}>
          Page URL to scan and fix
        </label>
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://panaum.github.io/linkspy-selfheal-test/"
          className="rounded-lg px-3 py-2 text-sm outline-none"
          style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: "#fff" }}
        />

        <button
          onClick={run}
          disabled={running || !repo.trim() || !url.trim()}
          className="cursor-pointer mt-1 flex items-center justify-center gap-2"
          style={{
            padding: "10px 16px", borderRadius: 10, fontSize: 14, fontWeight: 600,
            border: "1px solid rgba(168,85,247,0.4)",
            background: !repo.trim() || !url.trim() ? "rgba(255,255,255,0.04)" : "rgba(168,85,247,0.18)",
            color: !repo.trim() || !url.trim() ? "rgba(255,255,255,0.3)" : "#c084fc",
          }}
        >
          {running ? <Loader2 size={15} className="animate-spin" /> : <Wrench size={15} />}
          {running ? "Scanning and fixing…" : "Run self-heal"}
        </button>
      </div>

      {/* The result — a PR link, a refusal reason, or "nothing provable". */}
      {result && (
        <div className="mt-3 pt-3" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
          {prs.length > 0 ? (
            <div>
              <div className="flex items-center gap-2 mb-2" style={{ color: "#4ade80", fontSize: 13, fontWeight: 500 }}>
                <CheckCircle2 size={15} /> Opened {prs.length} pull request{prs.length > 1 ? "s" : ""} — review and merge to apply the fix.
              </div>
              {prs.map((pr) => (
                <a
                  key={pr.branch}
                  href={pr.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 py-1"
                  style={{ color: "#c084fc", fontSize: 13, textDecoration: "none" }}
                >
                  <GitPullRequest size={14} /> {pr.url.replace("https://github.com/", "")} · {pr.edits} fix{pr.edits > 1 ? "es" : ""}
                </a>
              ))}
            </div>
          ) : refused ? (
            <p style={{ fontSize: 12, color: "#fca5a5", margin: 0 }}>
              Refused: {String(result.refused)}
            </p>
          ) : result.error ? (
            <p style={{ fontSize: 12, color: "#fca5a5", margin: 0 }}>{result.error}</p>
          ) : (
            <p style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", margin: 0 }}>
              {result.note || "Nothing provable to fix on that page — no PR opened."}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
