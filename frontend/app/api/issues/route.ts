import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url");

  if (!url) {
    return NextResponse.json({ error: "Missing url parameter" }, { status: 400 });
  }

  const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";

  try {
    const res = await fetch(`${backendUrl}/uptime?url=${encodeURIComponent(url)}`, {
      cache: "no-store",
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to connect to backend";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
