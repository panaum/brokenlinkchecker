import { backendAuthHeaders } from "@/lib/backendToken";
import { NextRequest } from "next/server";
const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(_req: NextRequest) {
  try {
    const res = await fetch(`${backend()}/api/qa-bridge/keys`, {
      cache: "no-store", headers: await backendAuthHeaders() });
    return new Response(await res.text(), { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch (e) { return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "failed" }), { status: 500 }); }
}

export async function POST(req: NextRequest) {
  const body = await req.text();
  try {
    const res = await fetch(`${backend()}/api/qa-bridge/keys`, {
      method: "POST", cache: "no-store", body,
      headers: { ...(await backendAuthHeaders()), "Content-Type": "application/json" } });
    return new Response(await res.text(), { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch (e) { return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "failed" }), { status: 500 }); }
}
