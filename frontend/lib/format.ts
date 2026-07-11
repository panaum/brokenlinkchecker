// Shared formatting primitives for the detail standard. Keep display logic here
// so every surface truncates URLs, colors latency, and phrases time the same way.

/**
 * Middle-truncate a URL so the domain AND the final path segment stay visible:
 *   https://apexure.com/blog/2019/old-pricing  ->  apexure.com/…/old-pricing
 * Returns the display string; keep the full URL for the tooltip/copy.
 */
export function middleTruncateUrl(raw: string, max = 48): string {
  let host = raw;
  let path = "";
  try {
    const u = new URL(raw);
    host = u.hostname.replace(/^www\./, "");
    path = u.pathname + u.search;
  } catch {
    // Not a URL — fall back to a plain middle-truncate.
    if (raw.length <= max) return raw;
    const half = Math.floor((max - 1) / 2);
    return `${raw.slice(0, half)}…${raw.slice(-half)}`;
  }
  const segments = path.split("/").filter(Boolean);
  const last = segments.length ? segments[segments.length - 1] : "";
  const head = host;
  const full = last ? `${head}/${segments.join("/")}` : head;
  if (full.length <= max) return full;
  // Always keep domain + last segment; collapse the middle.
  const tail = last ? `/…/${last}` : "";
  const budget = max - tail.length;
  const shownHead = head.length > budget ? head.slice(0, Math.max(6, budget)) : head;
  return `${shownHead}${tail}`;
}

/** Green < 300ms, amber < 1000ms, red >= 1000ms. Null -> muted. */
export function latencyColor(ms: number | null | undefined): string {
  if (ms == null) return "var(--text-muted)";
  if (ms < 300) return "var(--signal)";
  if (ms < 1000) return "var(--status-attention)";
  return "var(--status-broken)";
}

const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

/** "just now" / "2h ago" / "3d ago". */
export function relativeTime(iso: string | number | Date, now: number = Date.now()): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const diff = now - t;
  if (diff < MIN) return "just now";
  if (diff < HOUR) return `${Math.floor(diff / MIN)}m ago`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h ago`;
  return `${Math.floor(diff / DAY)}d ago`;
}

/** Full local timestamp for the hover title. */
export function absoluteTime(iso: string | number | Date): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

/**
 * Phrase a scheduled overnight scan as "checked overnight" rather than a raw
 * 3AM time (which reads as an alarming anomaly to a client). Local hours 0-5.
 */
export function phraseScheduled(iso: string | number | Date, now: number = Date.now()): string {
  const d = new Date(iso);
  const h = d.getHours();
  if (h >= 0 && h < 6) return "checked overnight";
  return relativeTime(iso, now);
}

/**
 * Copy BOTH rich HTML and plain text so a paste lands formatted in Gmail and
 * clean in Slack / editors. Falls back to plain-text writeText.
 */
export async function copyRich(text: string, html?: string): Promise<boolean> {
  try {
    if (html && typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([html], { type: "text/html" }),
          "text/plain": new Blob([text], { type: "text/plain" }),
        }),
      ]);
      return true;
    }
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      return false;
    }
  }
}

/**
 * Split two URLs into a shared prefix, the changed middle, and a shared suffix,
 * so a fix can show the old segment struck and the new segment highlighted
 * instead of two full URLs. Compares on path segments.
 */
export function urlSegmentDiff(oldUrl: string, newUrl: string): {
  prefix: string; oldMid: string; newMid: string; suffix: string;
} {
  const norm = (u: string) => {
    try {
      const x = new URL(u);
      return { base: x.hostname.replace(/^www\./, ""), segs: x.pathname.split("/").filter(Boolean) };
    } catch {
      return { base: "", segs: u.split("/").filter(Boolean) };
    }
  };
  const a = norm(oldUrl);
  const b = norm(newUrl);
  // Shared leading segments.
  let i = 0;
  while (i < a.segs.length && i < b.segs.length && a.segs[i] === b.segs[i]) i++;
  // Shared trailing segments.
  let j = 0;
  while (
    j < a.segs.length - i && j < b.segs.length - i &&
    a.segs[a.segs.length - 1 - j] === b.segs[b.segs.length - 1 - j]
  ) j++;
  const prefixSegs = a.segs.slice(0, i);
  const oldMid = a.segs.slice(i, a.segs.length - j).join("/");
  const newMid = b.segs.slice(i, b.segs.length - j).join("/");
  const suffixSegs = a.segs.slice(a.segs.length - j);
  const base = a.base || b.base;
  const prefix = [base, ...prefixSegs].filter(Boolean).join("/") + (prefixSegs.length || base ? "/" : "");
  const suffix = suffixSegs.length ? "/" + suffixSegs.join("/") : "";
  return { prefix, oldMid, newMid, suffix };
}
