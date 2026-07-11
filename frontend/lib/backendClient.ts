// Client-side token helpers. Two token sources feed the same backend:
//  - staff: minted from the NextAuth session via /api/auth/backend-token
//  - client (portal): issued by invite-accept, kept in localStorage
// Both are HS256 tokens the backend verifies; only matters when PORTAL_ENFORCE
// is on (the backend ignores them otherwise), so this is safe to wire now.

let staffCache: { token: string; exp: number } | null = null;

function jwtExp(token: string): number {
  try {
    const payload = JSON.parse(
      atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")),
    );
    return typeof payload.exp === "number" ? payload.exp : 0;
  } catch {
    return 0;
  }
}

/** A fresh staff token (cached until ~30s before expiry). "" if not signed in. */
export async function staffToken(): Promise<string> {
  const now = Date.now() / 1000;
  if (staffCache && staffCache.exp > now + 30) return staffCache.token;
  try {
    const res = await fetch("/api/auth/backend-token", { cache: "no-store" });
    if (!res.ok) return "";
    const { token } = await res.json();
    if (!token) return "";
    staffCache = { token, exp: jwtExp(token) || now + 3600 };
    return token;
  } catch {
    return "";
  }
}

// ── Portal (client_viewer) session token ──
const PORTAL_KEY = "linkspy:portal-token";

export function setPortalToken(t: string): void {
  try { localStorage.setItem(PORTAL_KEY, t); } catch { /* ignore */ }
}
export function getPortalToken(): string {
  try { return localStorage.getItem(PORTAL_KEY) || ""; } catch { return ""; }
}
export function clearPortalToken(): void {
  try { localStorage.removeItem(PORTAL_KEY); } catch { /* ignore */ }
}

/** Append a token to a URL as `token=` (for EventSource, which can't set headers). */
export function withToken(url: string, token: string): string {
  if (!token) return url;
  return url + (url.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(token);
}
