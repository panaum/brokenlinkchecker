import { NextRequest } from "next/server";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// Portal dashboard — forwards the CLIENT's portal token (sent by the browser as
// Authorization) to the backend, which scopes the sites to their client when
// PORTAL_ENFORCE is on.
export async function GET(req: NextRequest) {
  const auth = req.headers.get("authorization") || "";
  try {
    const res = await fetch(`${backend()}/dashboard`, {
      cache: "no-store",
      headers: auth ? { Authorization: auth } : {},
    });
    return new Response(await res.text(), {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return new Response(JSON.stringify({ sites: [] }), { status: 200 });
  }
}
