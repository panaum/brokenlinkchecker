"use client";

/*
 * Phase 4 — the undesigned states: scan blocked, first run, empty results.
 * Mocked/demo (no backend wiring); matches the issue-primitive reference.
 * The backend half of Phase 4 — typed crawler errors
 * (blocked_cloudflare | rate_limited | timeout | dns_failure), the 1-req/sec
 * throttle, and persisting failed scans — is a separate task these consume.
 */
import { useState } from "react";

// ─── Scan blocked / failed ───────────────────────────────────────────────────
// Typed error -> cause copy. Warm, never red: nothing is wrong with their site.
const BLOCKED_COPY: Record<string, { icon: string; title: string; body: string }> = {
  blocked_cloudflare: {
    icon: "⚠",
    title: "The site turned us away",
    body: "smilelabny.com returned a Cloudflare challenge on the first three requests. This usually means bot protection is treating our crawler as suspicious. Nothing is wrong with your site.",
  },
  rate_limited: {
    icon: "⚠",
    title: "The site asked us to slow down",
    body: "smilelabny.com answered with 429 Too Many Requests. The host is rate-limiting our crawler, not blocking it — a slower pass usually gets through.",
  },
  timeout: {
    icon: "⚠",
    title: "The site didn’t respond in time",
    body: "Requests to smilelabny.com timed out. The server may be slow or briefly down; a retry at a gentler pace often clears it.",
  },
  dns_failure: {
    icon: "⚠",
    title: "We couldn’t find the site",
    body: "smilelabny.com didn’t resolve in DNS. Double-check the domain spelling — if it’s right, the DNS record may be propagating.",
  },
};

export function BlockedState({ errorType = "blocked_cloudflare" }: { errorType?: string }) {
  const [copied, setCopied] = useState(false);
  const c = BLOCKED_COPY[errorType] ?? BLOCKED_COPY.blocked_cloudflare;

  const copyIp = async () => {
    try { await navigator.clipboard.writeText("51.20.144.18"); } catch { /* noop */ }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  return (
    <div className="state">
      <div className="state-icon err" aria-hidden>{c.icon}</div>
      <h2>{c.title}</h2>
      <p>{c.body}</p>
      <div className="state-actions">
        <button className="btn-primary">Retry slowly</button>
        <button className="btn-sec">Scan with a browser user agent</button>
      </div>
      <div className="remedy">
        <div className="remedy-head">WHAT USUALLY WORKS</div>
        <div className="remedy-row">
          <span className="remedy-n">1</span>
          <div className="remedy-b">
            <div className="remedy-t">Retry at one request per second</div>
            <div className="remedy-d">Slower crawls clear most rate limits. Takes about 4 minutes for 142 links.</div>
          </div>
          <button className="btn-sec" style={{ height: 32 }}>Run</button>
        </div>
        <div className="remedy-row">
          <span className="remedy-n">2</span>
          <div className="remedy-b">
            <div className="remedy-t">Allowlist our IP</div>
            <div className="remedy-d mono">51.20.144.18 — add to Cloudflare, WAF or the host firewall.</div>
          </div>
          <button className="btn-sec" style={{ height: 32 }} onClick={copyIp}>{copied ? "Copied ✓" : "Copy"}</button>
        </div>
        <div className="remedy-row">
          <span className="remedy-n">3</span>
          <div className="remedy-b">
            <div className="remedy-t">Use the last good scan</div>
            <div className="remedy-d">20 July, 142 links, 4 issues. Still useful for the client call.</div>
          </div>
          <button className="btn-sec" style={{ height: 32 }}>Open</button>
        </div>
      </div>
    </div>
  );
}

// ─── First run ───────────────────────────────────────────────────────────────
export function FirstRunState() {
  const [url, setUrl] = useState("");
  return (
    <div className="state">
      <div className="state-icon new" aria-hidden>✦</div>
      <h2>Check your first site</h2>
      <p>Paste any URL and LinkSpy crawls every nav link, footer, CTA and body link, then keeps track of what is broken across future scans.</p>
      <div className="scan-card">
        <div className="scan-row">
          <input className="field mono" type="url" placeholder="https://your-client.com" aria-label="URL to scan"
            value={url} onChange={(e) => setUrl(e.target.value)} />
          <button className="btn-primary">Scan page</button>
        </div>
        <div className="chips">
          <span>Try one of ours:</span>
          <button className="chip mono" onClick={() => setUrl("https://apexure.com")}>apexure.com</button>
          <button className="chip mono" onClick={() => setUrl("https://smilelabny.com")}>smilelabny.com</button>
        </div>
      </div>
      <div className="remedy">
        <div className="remedy-head">SET UP ONCE, THEN IT RUNS ITSELF</div>
        <div className="remedy-row">
          <span className="remedy-n">1</span>
          <div className="remedy-b">
            <div className="remedy-t">Add your clients</div>
            <div className="remedy-d">Group sites so scans and reports are filed under the right account.</div>
          </div>
          <button className="btn-sec" style={{ height: 32 }}>Add</button>
        </div>
        <div className="remedy-row">
          <span className="remedy-n">2</span>
          <div className="remedy-b">
            <div className="remedy-t">Connect GA4</div>
            <div className="remedy-d">Traffic data ranks issues by how many people actually hit them.</div>
          </div>
          {/* Stubbed — the GA4 integration is Phase 5. Honestly labelled, not a dead button. */}
          <button className="btn-sec" style={{ height: 32 }} disabled title="Available in Phase 5">Soon</button>
        </div>
        <div className="remedy-row">
          <span className="remedy-n">3</span>
          <div className="remedy-b">
            <div className="remedy-t">Turn on monitoring</div>
            <div className="remedy-d">We re-check every 6 hours and email you only when something changes.</div>
          </div>
          <button className="btn-sec" style={{ height: 32 }}>Enable</button>
        </div>
      </div>
    </div>
  );
}

// ─── Empty results (scan succeeded, zero issues) ─────────────────────────────
// Short and quiet. No three-column layout.
export function EmptyState({ links = 142, site = "smilelabny.com" }: { links?: number; site?: string }) {
  return (
    <div className="empty">
      <div className="empty-badge" aria-hidden>✓</div>
      <h2>All {links.toLocaleString()} links healthy</h2>
      <p className="mono">{site} · re-scanned just now · no issues found</p>
    </div>
  );
}
