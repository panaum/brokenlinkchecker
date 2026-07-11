import { backendAuthHeaders } from "@/lib/backendToken";
import { NextRequest } from "next/server";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// Read-only: is self-heal armed, and on which repos. Touches no repo.
export async function GET(_req: NextRequest) {
  try {
    const res = await fetch(`${backend()}/api/self-heal/status`, { cache: "no-store", headers: await backendAuthHeaders() });
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
