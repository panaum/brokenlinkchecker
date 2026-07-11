import { backendAuthHeaders } from "@/lib/backendToken";
import { NextRequest } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/app/api/auth/[...nextauth]/route";

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url");

  if (!url) {
    return new Response(
      JSON.stringify({ error: "Missing url parameter" }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }

  // Scans are saved under the logged-in user's email, so history must be
  // looked up with the same email — otherwise the backend defaults to
  // "anonymous" and never matches the saved scans.
  const session = await getServerSession(authOptions);
  const email = session?.user?.email || "anonymous";

  const backendUrl =
    process.env.BACKEND_URL || "http://localhost:8000";

  try {
    const res = await fetch(
      `${backendUrl}/history?url=${encodeURIComponent(url)}&email=${encodeURIComponent(email)}`,
      { cache: "no-store", headers: await backendAuthHeaders() }
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
