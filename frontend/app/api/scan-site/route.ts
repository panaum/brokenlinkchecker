import { NextRequest } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/app/api/auth/[...nextauth]/route";

// Full-site scans stream for a long time. Keep the proxy function alive as long
// as the plan allows. The browser also connects directly to the backend when
// NEXT_PUBLIC_BACKEND_URL is set (see app/page.tsx), which avoids this limit
// entirely — this remains a fallback for local dev / same-origin requests.
export const runtime = "nodejs";
export const maxDuration = 300;

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url");

  if (!url) {
    return new Response(
      JSON.stringify({ type: "error", message: "Missing url parameter" }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }

  const session = await getServerSession(authOptions);
  const email = session?.user?.email || "anonymous";

  const backendUrl = `${
    process.env.BACKEND_URL || "http://localhost:8000"
  }/scan-site?url=${encodeURIComponent(url)}&email=${encodeURIComponent(email)}`;

  try {
    const upstream = await fetch(backendUrl, {
      headers: { Accept: "text/event-stream" },
      cache: "no-store",
    });

    if (!upstream.ok) {
      return new Response(
        `data: ${JSON.stringify({ type: "error", message: `Backend returned ${upstream.status}` })}\n\n`,
        { status: 200, headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" } }
      );
    }

    return new Response(upstream.body, {
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" },
    });
  } catch (err) {
    const message = err instanceof Error 
      ? `${err.message} (Target: ${backendUrl})` 
      : `Failed to connect to backend (Target: ${backendUrl})`;
    return new Response(
      `data: ${JSON.stringify({ type: "error", message })}\n\n`,
      { status: 200, headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" } }
    );
  }
}
