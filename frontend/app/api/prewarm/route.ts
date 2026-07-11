import { NextRequest } from "next/server";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// Anticipatory pre-warm: primes DNS/TLS for a URL the user is about to scan.
// Best-effort — never errors the UI.
export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url") || "";
  if (!url) return new Response(JSON.stringify({ warmed: false }), { status: 200 });
  try {
    const res = await fetch(`${backend()}/api/prewarm?url=${encodeURIComponent(url)}`, {
      cache: "no-store",
    });
    return new Response(await res.text(), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return new Response(JSON.stringify({ warmed: false }), { status: 200 });
  }
}
