import crypto from "crypto";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/app/api/auth/[...nextauth]/route";

// Server-only: mint the HS256 token the backend verifies, from the staff session.
// Used by the /api/auth/backend-token route and by the proxy routes (so the
// backend gets a verified identity instead of a spoofable email param).

function secret(): string {
  return process.env.BACKEND_AUTH_SECRET || process.env.NEXTAUTH_SECRET || "";
}

function b64url(input: string): string {
  return Buffer.from(input).toString("base64url");
}

export function mintToken(email: string, ttlSeconds = 3600): string {
  const key = secret();
  if (!key) return "";
  const now = Math.floor(Date.now() / 1000);
  const header = b64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = b64url(JSON.stringify({ email: email.toLowerCase(), iat: now, exp: now + ttlSeconds }));
  const data = `${header}.${payload}`;
  const sig = crypto.createHmac("sha256", key).update(data).digest("base64url");
  return `${data}.${sig}`;
}

/** Authorization header for a server-side call to the backend, from the current
 *  staff session. Empty object if not signed in / no secret (backend then
 *  treats the call as anonymous, which only matters when PORTAL_ENFORCE is on). */
export async function backendAuthHeaders(): Promise<Record<string, string>> {
  const session = await getServerSession(authOptions);
  const email = session?.user?.email;
  const token = email ? mintToken(email) : "";
  return token ? { Authorization: `Bearer ${token}` } : {};
}
