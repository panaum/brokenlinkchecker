import { NextRequest } from "next/server";
import { backendAuthHeaders } from "@/lib/backendToken";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// One report. Forwards the client's portal token if present (Authorization),
// else falls back to the staff session token — so both the agency and the
// client can open it.
export async function GET(req: NextRequest, { params }: { params: Promise<{ report_id: string }> }) {
  const { report_id } = await params;
  const clientAuth = req.headers.get("authorization");
  const headers = clientAuth ? { Authorization: clientAuth } : await backendAuthHeaders();
  try {
    const res = await fetch(`${backend()}/api/reports/${report_id}`, { cache: "no-store", headers });
    return new Response(await res.text(), { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch (e) {
    return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "failed" }), { status: 500 });
  }
}
