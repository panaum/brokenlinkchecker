import { backendAuthHeaders } from "@/lib/backendToken";
import { NextRequest } from "next/server";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// The uptime record for one site: last checked, current health, healthy streak,
// recent change events, and the weekly digest.
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ site_id: string }> },
) {
  const { site_id } = await params;
  try {
    const res = await fetch(`${backend()}/api/sites/${site_id}/monitoring`, {
      cache: "no-store",
      headers: await backendAuthHeaders(),
    });
    const data = await res.json();
    return new Response(JSON.stringify(data), {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to reach backend";
    return new Response(JSON.stringify({ error: message }), { status: 500 });
  }
}

// Toggle monitoring on/off and optionally change the cadence.
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ site_id: string }> },
) {
  const { site_id } = await params;
  const body = await req.json().catch(() => ({}));
  const enabled = Boolean(body.enabled);
  const freq = typeof body.freq === "string" ? body.freq : "";
  const qs = new URLSearchParams({ enabled: String(enabled) });
  if (freq) qs.set("freq", freq);
  try {
    const res = await fetch(
      `${backend()}/api/sites/${site_id}/monitoring?${qs.toString()}`,
      { method: "POST", cache: "no-store", headers: await backendAuthHeaders() },
    );
    const data = await res.json();
    return new Response(JSON.stringify(data), {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to reach backend";
    return new Response(JSON.stringify({ error: message }), { status: 500 });
  }
}
