import { NextRequest } from "next/server";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// Public status badge SVG. Proxied so it can be embedded from the app origin.
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ site_id: string }> },
) {
  const { site_id } = await params;
  try {
    const res = await fetch(`${backend()}/api/sites/${site_id}/badge.svg`, {
      cache: "no-store",
    });
    const svg = await res.text();
    return new Response(svg, {
      status: res.status,
      headers: {
        "Content-Type": "image/svg+xml",
        "Cache-Control": "public, max-age=300, s-maxage=300",
      },
    });
  } catch {
    return new Response("", { status: 502 });
  }
}
