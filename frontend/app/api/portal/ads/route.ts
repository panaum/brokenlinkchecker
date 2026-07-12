import { NextRequest } from "next/server";
const backend = () => process.env.BACKEND_URL || "http://localhost:8000";
export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization") || "";
  try {
    const res = await fetch(`${backend()}/api/portal/ads`, { cache: "no-store", headers: auth ? { Authorization: auth } : {} });
    return new Response(await res.text(), { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch { return new Response(JSON.stringify({ empty: true, all_clear: false, total: 0, campaigns: [], breaches: [], spend: { daily_at_risk: null, since_detected: null } }), { status: 200 }); }
}
