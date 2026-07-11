import { backendAuthHeaders } from "@/lib/backendToken";
import { NextRequest } from "next/server";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// Run the real monitored-scan path once, now, and report what it decided.
export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ site_id: string }> },
) {
  const { site_id } = await params;
  try {
    const res = await fetch(`${backend()}/api/sites/${site_id}/monitoring/run-now`, {
      method: "POST",
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
