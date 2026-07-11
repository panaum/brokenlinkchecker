import { NextRequest } from "next/server";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// On-demand X-ray capture for a URL. Best-effort — the backend returns
// { available: false } rather than erroring when capture isn't possible.
export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url") || "";
  if (!url) {
    return new Response(JSON.stringify({ available: false, error: "missing url" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }
  try {
    const res = await fetch(`${backend()}/api/xray?url=${encodeURIComponent(url)}`, {
      cache: "no-store",
    });
    const data = await res.json();
    return new Response(JSON.stringify(data), {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to reach backend";
    return new Response(JSON.stringify({ available: false, error: message }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }
}
