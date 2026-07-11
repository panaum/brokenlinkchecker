import { NextRequest } from "next/server";
import { backendAuthHeaders } from "@/lib/backendToken";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

export async function GET() {
  try {
    const res = await fetch(`${backend()}/api/invites`, {
      cache: "no-store",
      headers: await backendAuthHeaders(),
    });
    return new Response(await res.text(), {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return new Response(JSON.stringify({ invites: [] }), { status: 200 });
  }
}

export async function POST(req: NextRequest) {
  const email = req.nextUrl.searchParams.get("email") || "";
  const client_id = req.nextUrl.searchParams.get("client_id") || "";
  try {
    const res = await fetch(
      `${backend()}/api/invites?email=${encodeURIComponent(email)}&client_id=${encodeURIComponent(client_id)}`,
      { method: "POST", headers: await backendAuthHeaders(), cache: "no-store" },
    );
    return new Response(await res.text(), {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to reach backend";
    return new Response(JSON.stringify({ error: message }), { status: 500 });
  }
}
