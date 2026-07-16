// ═══════════════════════════════════════════════════════════════════════════
// SPINE HANDOFF v1 — signed cross-app deep links (no login wall). Shared file,
// duplicated verbatim in both frontends:
//   LinkSpy:   frontend/lib/handoff-contract.ts  (this file)
//   Dashboard: src/lib/handoff-contract.ts
// HANDOFF_CHECKSUM (sha256 of the canonical spec): must match in both.
//
// Security posture: the token REMOVES FRICTION, it is NOT auth. It never creates
// a session by itself — /handoff verifies sig+exp, then either forwards a browser
// that already has a session, or sends it to sign-in with callbackUrl. A stolen
// token only lets someone reach a sign-in page for a path; it grants nothing.
// ═══════════════════════════════════════════════════════════════════════════
import { createHmac, timingSafeEqual, randomBytes } from "node:crypto";

export const HANDOFF_CHECKSUM =
  "90b6a00da54c193c9142e31d8d8529a718dbb7933825b18f27162418a9ac7374";
export const HANDOFF_MAX_TTL_S = 300; // ≤ 5 minutes

type Payload = { target_path: string; exp: number; nonce: string };

const b64url = (s: string) => Buffer.from(s, "utf8").toString("base64url");
const unb64url = (s: string) => Buffer.from(s, "base64url").toString("utf8");

// Sign a short-lived token for a target PATH (must be app-relative, starts "/").
export function signHandoff(targetPath: string, secret: string, nowSeconds: number, ttlS = HANDOFF_MAX_TTL_S): string {
  const exp = nowSeconds + Math.min(ttlS, HANDOFF_MAX_TTL_S);
  const payload: Payload = { target_path: targetPath, exp, nonce: randomBytes(8).toString("hex") };
  const body = b64url(JSON.stringify(payload));
  const sig = createHmac("sha256", secret).update(body).digest("hex");
  return `${body}.${sig}`;
}

export function verifyHandoff(
  token: string, secret: string, nowSeconds: number,
): { ok: true; targetPath: string } | { ok: false; reason: string } {
  if (!token || !token.includes(".")) return { ok: false, reason: "malformed" };
  const dot = token.indexOf(".");
  const body = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  const expected = createHmac("sha256", secret).update(body).digest("hex");
  const a = Buffer.from(expected, "hex");
  const b = Buffer.from(sig, "hex");
  if (a.length !== b.length || !timingSafeEqual(a, b)) return { ok: false, reason: "bad signature" };
  let payload: Payload;
  try { payload = JSON.parse(unb64url(body)); } catch { return { ok: false, reason: "bad payload" }; }
  if (typeof payload.target_path !== "string" || !payload.target_path.startsWith("/")) return { ok: false, reason: "bad target" };
  if (typeof payload.exp !== "number" || nowSeconds > payload.exp) return { ok: false, reason: "expired" };
  return { ok: true, targetPath: payload.target_path };
}

// Full handoff URL: {base}/handoff?token=… — always sign SERVER-SIDE.
export function handoffUrl(base: string, targetPath: string, secret: string, nowSeconds: number): string {
  const token = signHandoff(targetPath, secret, nowSeconds);
  return `${base.replace(/\/$/, "")}/handoff?token=${encodeURIComponent(token)}`;
}
