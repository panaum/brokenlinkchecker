import { NextRequest } from "next/server";
import { backendAuthHeaders } from "@/lib/backendToken";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ resource_id: string }> }) {
  const { resource_id } = await params;
  const qs = req.nextUrl.searchParams.toString();
  try {
    const res = await fetch(`${backend()}/api/resources/${resource_id}?${qs}`, { method: "PATCH", cache: "no-store", headers: await backendAuthHeaders() });
    return new Response(await res.text(), { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch (e) { return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "failed" }), { status: 500 }); }
}

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ resource_id: string }> }) {
  const { resource_id } = await params;
  try {
    const res = await fetch(`${backend()}/api/resources/${resource_id}`, { method: "DELETE", cache: "no-store", headers: await backendAuthHeaders() });
    return new Response(await res.text(), { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch (e) { return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "failed" }), { status: 500 }); }
}
