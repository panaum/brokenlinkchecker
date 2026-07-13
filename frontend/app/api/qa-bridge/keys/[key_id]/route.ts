import { backendAuthHeaders } from "@/lib/backendToken";
import { NextRequest } from "next/server";
const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

export async function DELETE(_req: NextRequest, { params }: { params: Promise<{ key_id: string }> }) {
  const { key_id } = await params;
  try {
    const res = await fetch(`${backend()}/api/qa-bridge/keys/${key_id}`, {
      method: "DELETE", cache: "no-store", headers: await backendAuthHeaders() });
    return new Response(await res.text(), { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch (e) { return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "failed" }), { status: 500 }); }
}
