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

  const generateZip = async () => {
    if (count === 0) return;
    setGenerating(true);

    try {
      const now = new Date();
      const dateStr = now.toISOString().split("T")[0];

      // Generate .htaccess content
      const htaccessLines = [
        "# LinkSpy Redirect Rules",
        `# Generated: ${dateStr}`,
        "# Confidence threshold: 60%+",
        "",
      ];

      // Generate CSV content
      const csvLines = ["source,destination,confidence,type"];

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

        htaccessLines.push(`Redirect 301 ${oldPath} ${newPath}`);
        csvLines.push(`${oldPath},${newPath},${r.suggestion.confidence},301`);
      }

      const htaccessContent = htaccessLines.join("\n");
      const csvContent = csvLines.join("\n");

      // Use JSZip-like approach with raw zip creation
      // Simple zip implementation without external dependency
      const zip = await createZip([
        { name: "redirects.htaccess", content: htaccessContent },
        { name: "redirects.csv", content: csvContent },
      ]);

      const blob = new Blob([zip], { type: "application/zip" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `linkspy-redirects-${dateStr}.zip`;
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
      onClick={generateZip}
      disabled={isDisabled || generating}
      title={isDisabled ? "Scan a page first to generate redirects" : `Download redirect rules for ${count} broken links`}
      className="inline-flex items-center gap-2 px-4 py-2 rounded-xl transition-all cursor-pointer"
      style={{
        background: isDisabled ? "rgba(255,255,255,0.03)" : "rgba(96,165,250,0.12)",
        border: `1px solid ${isDisabled ? "rgba(255,255,255,0.06)" : "rgba(96,165,250,0.25)"}`,
        color: isDisabled ? "rgba(255,255,255,0.25)" : "#60a5fa",
        fontFamily: "var(--font-poppins), Poppins, sans-serif",
        fontWeight: 500,
        fontSize: "13px",
        opacity: isDisabled ? 0.5 : 1,
        cursor: isDisabled ? "not-allowed" : "pointer",
      }}
    >
      <Download size={14} />
      {generating ? "Generating…" : "Download Redirects"}
      {count > 0 && (
        <span
          style={{
            background: "rgba(96,165,250,0.2)",
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

// ─── Minimal ZIP file creator (no external deps) ─────────────────────────────

async function createZip(files: { name: string; content: string }[]): Promise<Uint8Array> {
  const encoder = new TextEncoder();
  const parts: Uint8Array[] = [];
  const centralDir: Uint8Array[] = [];
  let offset = 0;

  for (const file of files) {
    const nameBytes = encoder.encode(file.name);
    const dataBytes = encoder.encode(file.content);
    const crc = crc32(dataBytes);

    // Local file header
    const localHeader = new Uint8Array(30 + nameBytes.length);
    const lv = new DataView(localHeader.buffer);
    lv.setUint32(0, 0x04034b50, true); // signature
    lv.setUint16(4, 20, true); // version needed
    lv.setUint16(6, 0, true); // flags
    lv.setUint16(8, 0, true); // compression (store)
    lv.setUint16(10, 0, true); // mod time
    lv.setUint16(12, 0, true); // mod date
    lv.setUint32(14, crc, true); // crc32
    lv.setUint32(18, dataBytes.length, true); // compressed size
    lv.setUint32(22, dataBytes.length, true); // uncompressed size
    lv.setUint16(26, nameBytes.length, true); // filename length
    lv.setUint16(28, 0, true); // extra field length
    localHeader.set(nameBytes, 30);

    parts.push(localHeader);
    parts.push(dataBytes);

    // Central directory entry
    const cdEntry = new Uint8Array(46 + nameBytes.length);
    const cv = new DataView(cdEntry.buffer);
    cv.setUint32(0, 0x02014b50, true); // signature
    cv.setUint16(4, 20, true); // version made by
    cv.setUint16(6, 20, true); // version needed
    cv.setUint16(8, 0, true); // flags
    cv.setUint16(10, 0, true); // compression
    cv.setUint16(12, 0, true); // mod time
    cv.setUint16(14, 0, true); // mod date
    cv.setUint32(16, crc, true); // crc32
    cv.setUint32(20, dataBytes.length, true); // compressed size
    cv.setUint32(24, dataBytes.length, true); // uncompressed size
    cv.setUint16(28, nameBytes.length, true); // filename length
    cv.setUint16(30, 0, true); // extra field length
    cv.setUint16(32, 0, true); // comment length
    cv.setUint16(34, 0, true); // disk number
    cv.setUint16(36, 0, true); // internal attrs
    cv.setUint32(38, 0, true); // external attrs
    cv.setUint32(42, offset, true); // local header offset
    cdEntry.set(nameBytes, 46);

    centralDir.push(cdEntry);
    offset += localHeader.length + dataBytes.length;
  }

  const cdOffset = offset;
  let cdSize = 0;
  for (const cd of centralDir) {
    parts.push(cd);
    cdSize += cd.length;
  }

  // End of central directory
  const eocd = new Uint8Array(22);
  const ev = new DataView(eocd.buffer);
  ev.setUint32(0, 0x06054b50, true); // signature
  ev.setUint16(4, 0, true); // disk number
  ev.setUint16(6, 0, true); // cd disk
  ev.setUint16(8, files.length, true); // entries on disk
  ev.setUint16(10, files.length, true); // total entries
  ev.setUint32(12, cdSize, true); // cd size
  ev.setUint32(16, cdOffset, true); // cd offset
  ev.setUint16(20, 0, true); // comment length
  parts.push(eocd);

  // Concatenate
  const totalLength = parts.reduce((sum, p) => sum + p.length, 0);
  const result = new Uint8Array(totalLength);
  let pos = 0;
  for (const p of parts) {
    result.set(p, pos);
    pos += p.length;
  }
  return result;
}

function crc32(data: Uint8Array): number {
  let crc = 0xffffffff;
  for (let i = 0; i < data.length; i++) {
    crc ^= data[i];
    for (let j = 0; j < 8; j++) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}
