import { NextRequest } from "next/server";

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url");

  if (!url) {
    return new Response(
      JSON.stringify({ error: "Missing url parameter" }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }

  const backendUrl = `${
    process.env.BACKEND_URL || "http://localhost:8000"
  }/preview?url=${encodeURIComponent(url)}`;

  try {
    const upstream = await fetch(backendUrl, { cache: "no-store" });

    if (!upstream.ok) {
      return new Response(
        JSON.stringify({ error: `Backend returned ${upstream.status}` }),
        { status: upstream.status, headers: { "Content-Type": "application/json" } }
      );
    }

    const data = await upstream.json();
    return new Response(JSON.stringify(data), {
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to connect to backend";
    return new Response(
      JSON.stringify({ error: message }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}
