"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { LinkResult } from "@/types";

interface RedirectDownloadProps {
  results: LinkResult[];
}

export default function RedirectDownloadButton({ results }: RedirectDownloadProps) {
  const [generating, setGenerating] = useState(false);

  // Get broken links with suggestions >= 60 confidence
  const redirectable = results.filter(
    (r) =>
      r.label === "broken" &&
      r.suggestion?.suggested_url &&
      (r.suggestion?.confidence ?? 0) >= 60
  );

  const count = redirectable.length;

  const generateFile = () => {
    if (count === 0) return;
    setGenerating(true);

    try {
      const now = new Date();
      const dateStr = now.toISOString().split("T")[0];

      const lines = [
        "# LinkSpy Redirect Rules",
        `# Generated: ${dateStr}`,
        "",
      ];

      for (const r of redirectable) {
        if (!r.suggestion?.suggested_url) continue;

        let oldPath = "/";
        let newPath = "/";
        try {
          oldPath = new URL(r.url).pathname;
        } catch { oldPath = r.url; }
        try {
          newPath = new URL(r.suggestion.suggested_url).pathname;
        } catch { newPath = r.suggestion.suggested_url; }

        lines.push(`Redirect 301 ${oldPath} ${newPath}`);
      }

      const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "redirects.txt";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } finally {
      setGenerating(false);
    }
  };

  const isDisabled = count === 0;

  return (
    <button
      onClick={generateFile}
      disabled={isDisabled || generating}
      title={isDisabled ? "Scan a page first to generate redirects" : `Download redirect rules for ${count} broken links`}
      className="inline-flex items-center gap-2 px-4 py-2 rounded-xl transition-all cursor-pointer"
      style={{
        background: isDisabled ? "var(--color-card-soft)" : "rgba(91,141,239,0.12)",
        border: `1px solid ${isDisabled ? "var(--color-border-soft)" : "rgba(91,141,239,0.3)"}`,
        color: isDisabled ? "var(--color-text-muted)" : "#5b8def",
        fontWeight: 500,
        fontSize: "13px",
        opacity: isDisabled ? 0.6 : 1,
        cursor: isDisabled ? "not-allowed" : "pointer",
      }}
    >
      <Download size={14} />
      {generating ? "Generating…" : "Download Redirects"}
      {count > 0 && (
        <span
          style={{
            background: "rgba(91,141,239,0.2)",
            borderRadius: 9999,
            padding: "1px 7px",
            fontSize: "11px",
            fontWeight: 600,
          }}
        >
          {count}
        </span>
      )}
    </button>
  );
}
