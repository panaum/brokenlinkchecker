import { backendAuthHeaders } from "@/lib/backendToken";
import { NextRequest } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/app/api/auth/[...nextauth]/route";

/**
 * Proxy for the backend's storage diagnostics.
 *
 * Exists so the answer to "is my scan history actually being saved?" is one
 * click on our own domain, rather than requiring the Railway hostname and the
 * exact email a scan was stored under. The session supplies the email, which is
 * the same one /api/scan saves under — a mismatch there is itself a common
 * cause of an empty History panel.
 *
 *   GET /api/diagnostics                       -> are the tables there?
 *   GET /api/diagnostics?url=https://acme.test -> how much of that site is stored?
 */
export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url") ?? "";
  // ?probe=1 attempts a real snapshot write (and deletes it again). Reads
  // succeeding while writes fail is the signature of row-level security.
  const probe = req.nextUrl.searchParams.get("probe");

  const session = await getServerSession(authOptions);
  const email = session?.user?.email || "anonymous";

  const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";
  const endpoint =
    probe && url
      ? "/api/diagnostics/snapshot-write-test"
      : "/api/diagnostics/diffing";
  const target =
    `${backendUrl}${endpoint}` +
    `?email=${encodeURIComponent(email)}` +
    (url ? `&url=${encodeURIComponent(url)}` : "");

  try {
    const res = await fetch(target, { cache: "no-store", headers: await backendAuthHeaders() });
    const data = await res.json();

    return new Response(
      JSON.stringify(
        {
          ...data,
          // Surfaced so an email mismatch between scanning and reading is
          // obvious rather than something to deduce.
          queried_as: email,
          signed_in: Boolean(session?.user?.email),
        },
        null,
        2,
      ),
      { status: res.status, headers: { "Content-Type": "application/json" } },
    );
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Failed to connect to backend";
    return new Response(
      JSON.stringify({ error: message, backend_configured: Boolean(process.env.BACKEND_URL) }, null, 2),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
}
