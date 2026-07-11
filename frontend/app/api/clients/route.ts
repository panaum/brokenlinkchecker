import { NextRequest } from "next/server";
import { backendAuthHeaders } from "@/lib/backendToken";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

export async function GET() {
  try {
    const res = await fetch(`${backend()}/api/clients`, {
      cache: "no-store",
      headers: await backendAuthHeaders(),
    });
    return new Response(await res.text(), {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return new Response(JSON.stringify({ clients: [] }), { status: 200 });
  }
}

export async function POST(req: NextRequest) {
  const name = req.nextUrl.searchParams.get("name") || "";
  try {
    const res = await fetch(`${backend()}/api/clients?name=${encodeURIComponent(name)}`, {
      method: "POST",
      headers: await backendAuthHeaders(),
      cache: "no-store",
    });
    return new Response(await res.text(), {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to reach backend";
    return new Response(JSON.stringify({ error: message }), { status: 500 });
  }
}
