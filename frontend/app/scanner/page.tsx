"use client";

/*
 * /scanner — the scan form on top, the three-column issue results below (mocked
 * via the shared ResultsView). One page, no navigation.
 */
import { useState } from "react";
import { Inter, JetBrains_Mono } from "next/font/google";
import { ResultsView } from "../issues/page";
import "../issues/issues.css";

const inter = Inter({ subsets: ["latin"], weight: ["400", "500", "600", "700", "800"] });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500"] });

export default function ScannerPage() {
  const [url, setUrl] = useState("https://smilelabny.com");

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
          <form className="scan-row" onSubmit={(e) => e.preventDefault()}>
            <input
              className="field mono"
              type="url"
              placeholder="https://your-client.com"
              aria-label="URL to scan"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <button className="btn-primary" type="submit">Scan page</button>
          </form>
        </div>

        {/* results (mocked) */}
        <ResultsView />
      </div>
    </div>
  );
}
