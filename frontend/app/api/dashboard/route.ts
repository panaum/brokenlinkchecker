import { backendAuthHeaders } from "@/lib/backendToken";
import { NextRequest } from "next/server";

export async function GET(req: NextRequest) {
  const backendUrl =
    process.env.BACKEND_URL || "http://localhost:8000";

  try {
    const res = await fetch(`${backendUrl}/dashboard`, {
      cache: "no-store",
      headers: await backendAuthHeaders(),
    });

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
