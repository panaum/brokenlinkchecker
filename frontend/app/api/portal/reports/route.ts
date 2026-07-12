import { NextRequest } from "next/server";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// Forwards the client's portal token; backend scopes to their client's sites.
export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization") || "";
  try {
    const res = await fetch(`${backend()}/api/portal/reports`, { cache: "no-store", headers: auth ? { Authorization: auth } : {} });
    return new Response(await res.text(), { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch { return new Response(JSON.stringify({ reports: [] }), { status: 200 }); }
}
