import { NextRequest } from "next/server";

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url");

  if (!url) {
    return new Response(
      JSON.stringify({ type: "error", message: "Missing url parameter" }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }

  const backendUrl = `${
    process.env.BACKEND_URL || "http://localhost:8000"
  }/scan?url=${encodeURIComponent(url)}`;

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
    const message = err instanceof Error ? err.message : "Failed to connect to backend";
    return new Response(
      `data: ${JSON.stringify({ type: "error", message })}\n\n`,
      { status: 200, headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" } }
    );
  }
}