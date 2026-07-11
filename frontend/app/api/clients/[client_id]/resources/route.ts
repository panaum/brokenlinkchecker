import { NextRequest } from "next/server";
import { backendAuthHeaders } from "@/lib/backendToken";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(_req: NextRequest, { params }: { params: Promise<{ client_id: string }> }) {
  const { client_id } = await params;
  try {
    const res = await fetch(`${backend()}/api/clients/${client_id}/resources`, { cache: "no-store", headers: await backendAuthHeaders() });
    return new Response(await res.text(), { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch { return new Response(JSON.stringify({ resources: [] }), { status: 200 }); }
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ client_id: string }> }) {
  const { client_id } = await params;
  const qs = req.nextUrl.searchParams.toString();
  try {
    const res = await fetch(`${backend()}/api/clients/${client_id}/resources?${qs}`, { method: "POST", cache: "no-store", headers: await backendAuthHeaders() });
    return new Response(await res.text(), { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch (e) { return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "failed" }), { status: 500 }); }
}
