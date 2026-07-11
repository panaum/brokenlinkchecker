import { backendAuthHeaders } from "@/lib/backendToken";
import { NextRequest } from "next/server";

export async function POST(req: NextRequest) {
  const body = await req.json() as { url?: string; email?: string };

  if (!body.url || !body.email) {
    return new Response(
      JSON.stringify({ error: "Missing url or email" }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }

  const backendUrl =
    process.env.BACKEND_URL || "http://localhost:8000";

  try {
    const res = await fetch(
      `${backendUrl}/register?url=${encodeURIComponent(body.url)}&email=${encodeURIComponent(body.email)}`,
      { method: "POST", cache: "no-store", headers: await backendAuthHeaders() }
    );

    const data = await res.json();

    return new Response(JSON.stringify(data), {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Failed to connect to backend";
    return new Response(JSON.stringify({ error: message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}
