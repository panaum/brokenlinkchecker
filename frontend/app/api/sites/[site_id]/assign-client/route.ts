import { NextRequest } from "next/server";
import { backendAuthHeaders } from "@/lib/backendToken";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// Assign (or clear) a site's client. Agency, member+.
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ site_id: string }> },
) {
  const { site_id } = await params;
  const client_id = req.nextUrl.searchParams.get("client_id") || "";
  try {
    const res = await fetch(
      `${backend()}/api/sites/${site_id}/assign-client?client_id=${encodeURIComponent(client_id)}`,
      { method: "POST", headers: await backendAuthHeaders(), cache: "no-store" },
    );
    return new Response(await res.text(), {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to reach backend";
    return new Response(JSON.stringify({ error: message }), { status: 500 });
  }
}
