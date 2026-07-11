import { ImageResponse } from "next/og";

// OG card for a shared report — mission-control aesthetic so the link unfurls
// beautifully in Slack / Gmail / iMessage.
export const runtime = "nodejs";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "LinkSpy report";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url || "site";
  }
}
// The score ring/numeral is BRAND purple (identity), not a status color.
function scoreColor(s: number | null): string {
  return s == null ? "#9aa0b4" : "#a855f7";
}

export default async function OgImage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  let domain = "site";
  let score: number | null = null;
  let broken = 0;
  let dead = 0;
  try {
    const res = await fetch(`${backend()}/api/r/${token}`, { cache: "no-store" });
    if (res.ok) {
      const r = await res.json();
      domain = domainOf(r.url);
      score = r.health_score ?? null;
      broken = r.broken_count ?? 0;
      dead = r.dead_cta_count ?? 0;
    }
  } catch {
    /* fall through to defaults */
  }

  const color = scoreColor(score);
  const verdict =
    broken > 0 ? `${broken} broken link${broken === 1 ? "" : "s"}` : dead > 0 ? `${dead} dead CTA${dead === 1 ? "" : "s"}` : "All clear";

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#0b0712",
          padding: 72,
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", color: "#e9f4f1", fontSize: 34, fontWeight: 800 }}>
          Link<span style={{ color: "#a855f7" }}>Spy</span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 56 }}>
          {/* score disc */}
          <div
            style={{
              width: 220,
              height: 220,
              borderRadius: 110,
              border: `14px solid ${color}`,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              color,
            }}
          >
            <div style={{ fontSize: 88, fontWeight: 800, lineHeight: 1 }}>{score ?? "--"}</div>
            <div style={{ fontSize: 24, color: "#8b9ba0" }}>/ 100</div>
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ fontSize: 30, color: "#8b9ba0" }}>{domain}</div>
            <div style={{ fontSize: 58, fontWeight: 800, color: "#e9f4f1", marginTop: 8 }}>{verdict}</div>
          </div>
        </div>

        <div style={{ display: "flex", color: "#8b9ba0", fontSize: 26 }}>Link health report</div>
      </div>
    ),
    { ...size },
  );
}
