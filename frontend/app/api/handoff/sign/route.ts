import { NextRequest, NextResponse } from "next/server";
import { handoffUrl } from "@/lib/handoff-contract";

// Sign an outbound handoff link (to the Dashboard) SERVER-SIDE so SPINE_SECRET
// never reaches the browser. POST { targetPath, base? } → { url }. base defaults
// to DASHBOARD_APP_URL. This route sits under the auth middleware, so only a
// signed-in agency user can mint links.
export async function POST(req: NextRequest) {
  const secret = process.env.SPINE_SECRET ?? "";
  if (!secret) return NextResponse.json({ error: "not configured" }, { status: 503 });
  let body: { targetPath?: string; base?: string };
  try { body = await req.json(); } catch { return NextResponse.json({ error: "bad json" }, { status: 400 }); }
  const targetPath = body.targetPath ?? "";
  if (!targetPath.startsWith("/")) return NextResponse.json({ error: "bad target" }, { status: 400 });
  const base = body.base || process.env.DASHBOARD_APP_URL || "";
  if (!base) return NextResponse.json({ error: "no target base" }, { status: 400 });
  return NextResponse.json({ url: handoffUrl(base, targetPath, secret, Math.floor(Date.now() / 1000)) });
}
