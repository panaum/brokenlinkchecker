import { NextRequest, NextResponse } from "next/server";
import { verifyHandoff } from "@/lib/handoff-contract";

// Inbound handoff from the Dashboard: verify the signed token, then forward. The
// token removes friction, it is NOT auth — it never mints a session. If the
// browser already has a NextAuth session, go straight to the target; otherwise
// send to NextAuth sign-in with callbackUrl. Tamper/expiry → home.
const SESSION_COOKIES = [
  "next-auth.session-token",
  "__Secure-next-auth.session-token",
  "authjs.session-token",
  "__Secure-authjs.session-token",
];

export async function GET(req: NextRequest) {
  const token = req.nextUrl.searchParams.get("token") ?? "";
  const secret = process.env.SPINE_SECRET ?? "";
  const home = new URL("/", req.url);
  if (!secret) return NextResponse.redirect(home);

  const v = verifyHandoff(token, secret, Math.floor(Date.now() / 1000));
  if (!v.ok) return NextResponse.redirect(home);

  const target = new URL(v.targetPath, req.url);
  const signedIn = SESSION_COOKIES.some((n) => req.cookies.get(n)?.value);
  if (signedIn) return NextResponse.redirect(target);

  const signin = new URL("/api/auth/signin", req.url);
  signin.searchParams.set("callbackUrl", target.toString());
  return NextResponse.redirect(signin);
}
