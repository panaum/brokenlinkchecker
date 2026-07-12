import { backendAuthHeaders } from "@/lib/backendToken";
import { NextRequest } from "next/server";
const backend = () => process.env.BACKEND_URL || "http://localhost:8000";
export async function GET(req: NextRequest, { params }: { params: Promise<{ site_id: string }> }) {
  const { site_id } = await params;
  try {
    const res = await fetch(`${backend()}/api/sites/${site_id}/crm`, { cache: "no-store", headers: await backendAuthHeaders() });
    return new Response(await res.text(), { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch (e) { return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "failed" }), { status: 500 }); }
}
