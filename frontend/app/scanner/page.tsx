"use client";

/*
 * /scanner — scan form on top, three-column issue results below (mocked).
 * The Scan button runs a mock scan: scanning -> results (or the empty / blocked
 * state when the URL calls for it). One page, no navigation.
 */
import { useRef, useState } from "react";
import { Inter, JetBrains_Mono } from "next/font/google";
import { ResultsView } from "../issues/page";
import { EmptyState, BlockedState } from "../issues/states";
import "../issues/issues.css";

const inter = Inter({ subsets: ["latin"], weight: ["400", "500", "600", "700", "800"] });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500"] });

type Phase = "results" | "scanning" | "empty" | "blocked";

// Mocked routing so every outcome is reachable from the form: a domain that
// looks Cloudflare-protected blocks; a "clean" one comes back healthy; anything
// else returns the issue set.
function outcomeFor(url: string): Exclude<Phase, "scanning"> {
  const u = url.toLowerCase();
  if (u.includes("cloudflare") || u.includes("blocked") || u.includes("vercel.app")) return "blocked";
  if (u.includes("clean") || u.includes("healthy") || u.includes("empty")) return "empty";
  return "results";
}

export default function ScannerPage() {
  const [url, setUrl] = useState("https://smilelabny.com");
  const [phase, setPhase] = useState<Phase>("results");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scan = () => {
    if (!url.trim()) return;
    setPhase("scanning");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setPhase(outcomeFor(url)), 1300);
  };

  const scanning = phase === "scanning";

  return (
    <div
      className={`issues-page ${inter.className}`}
      style={{ "--font-ui": inter.style.fontFamily, "--font-mono": mono.style.fontFamily } as React.CSSProperties}
    >
      <div className="issues-wrap">
        {/* scan form */}
        <div className="scan-panel">
          <h1 className="scan-title">Scan a page</h1>
          <p className="scan-desc">
            We crawl every nav link, footer, CTA and body link, then track what’s broken across scans.
          </p>
          <form className="scan-row" onSubmit={(e) => { e.preventDefault(); scan(); }}>
            <input
              className="field mono"
              type="url"
              placeholder="https://your-client.com"
              aria-label="URL to scan"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={scanning}
            />
            <button className="btn-primary" type="submit" disabled={scanning}>
              {scanning ? "Scanning…" : "Scan page"}
            </button>
          </form>
          {scanning && (
            <>
              <div className="scan-bar" aria-hidden><i /></div>
              <p className="scan-hint" role="status">Checking every link on {url} …</p>
            </>
          )}
        </div>

        {/* results / states (mocked) */}
        {phase === "results" && <ResultsView />}
        {phase === "empty" && <EmptyState site={url.replace(/^https?:\/\//, "")} />}
        {phase === "blocked" && <BlockedState />}
      </div>
    </div>
  );
}
