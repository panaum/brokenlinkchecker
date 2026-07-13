import { NextRequest } from "next/server";
const backend = () => process.env.BACKEND_URL || "http://localhost:8000";
export async function GET(req: NextRequest, { params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  try {
    const res = await fetch(`${backend()}/api/attest/${token}`, { cache: "no-store" });
    return new Response(await res.text(), { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch (e) { return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "failed" }), { status: 500 }); }
}
