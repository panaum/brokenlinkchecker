import { NextRequest } from "next/server";
const backend = () => process.env.BACKEND_URL || "http://localhost:8000";
export async function GET(req: NextRequest, { params }: { params: Promise<{ site_id: string }> }) {
  const { site_id } = await params;
  const auth = req.headers.get("authorization") || "";
  try {
    const res = await fetch(`${backend()}/api/sites/${site_id}/fragility/client`, { cache: "no-store", headers: auth ? { Authorization: auth } : {} });
    return new Response(await res.text(), { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch { return new Response(JSON.stringify({ visible: false }), { status: 200 }); }
}
