import { NextRequest } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/app/api/auth/[...nextauth]/route";

// Proxy to the FastAPI backend. The backend hostname is server-side only.
export const runtime = "nodejs";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return new Response(JSON.stringify({ error: "not signed in" }), { status: 401 });
  }

  const { id } = await params;
  const backend = process.env.BACKEND_URL || "http://localhost:8000";
  const query = req.nextUrl.search;
  const target = `${backend}/api/findings/${id}/client-message${query}`;

  try {
    const res = await fetch(target, { method: "GET", cache: "no-store" });
    const body = await res.text();
    return new Response(body, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("content-type") ?? "application/json" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "backend unreachable";
    return new Response(JSON.stringify({ error: message }), { status: 502 });
  }
}
