import { NextRequest, NextResponse } from "next/server";
import { handoffUrl } from "@/lib/handoff-contract";

// Cockpit Delivery proxy (Part C): fetch a site's linked pages from the Dashboard
// read API. Key stays server-side. 15-min cache + in-memory last-known-good, so
// the Dashboard being unreachable renders stale data ("as of …"), never an error.
// "Open in QA" links are signed here (server-side) with a fresh handoff token.
const CACHE_MS = 15 * 60 * 1000;
type Cached = { data: DeliveryData; at: number };
const cache = new Map<string, Cached>();

type DeliveryData = { registry_site_id: string; as_of: string; deliverables: Deliverable[] };
type Deliverable = {
  name: string; qa_page_ref: string; status: string;
  checklist: { passed: number; failed: number; na: number; total: number };
  qa_score: number | null; signed_off_at: string | null; deep_link_path: string;
};

function withHandoff(data: DeliveryData): DeliveryData & { deliverables: (Deliverable & { open_in_qa_url: string | null })[] } {
  const dashApp = (process.env.DASHBOARD_APP_URL || "").replace(/\/$/, "");
  const secret = process.env.SPINE_SECRET || "";
  const now = Math.floor(Date.now() / 1000);
  return {
    ...data,
    deliverables: (data.deliverables || []).map((d) => ({
      ...d,
      open_in_qa_url: dashApp && secret ? handoffUrl(dashApp, d.deep_link_path, secret, now) : null,
    })),
  };
}

export async function GET(req: NextRequest) {
  const siteId = req.nextUrl.searchParams.get("site_id");
  if (!siteId) return NextResponse.json({ error: "site_id required" }, { status: 400 });
  const base = (process.env.DASHBOARD_BRIDGE_URL || "").replace(/\/$/, "");
  const key = process.env.DASHBOARD_BRIDGE_KEY || "";
  if (!base || !key) return NextResponse.json({ unavailable: true, reason: "bridge not configured" });

  const cached = cache.get(siteId);
  if (cached && Date.now() - cached.at < CACHE_MS) {
    return NextResponse.json({ ...withHandoff(cached.data), stale: false });
  }
  try {
    const res = await fetch(`${base}/api/registry-bridge/delivery?registry_site_id=${encodeURIComponent(siteId)}`, {
      headers: { Authorization: `Bearer ${key}` }, signal: AbortSignal.timeout(8000), cache: "no-store",
    });
    if (!res.ok) throw new Error(`http ${res.status}`);
    const data = (await res.json()) as DeliveryData;
    cache.set(siteId, { data, at: Date.now() });
    return NextResponse.json({ ...withHandoff(data), stale: false });
  } catch {
    if (cached) return NextResponse.json({ ...withHandoff(cached.data), stale: true }); // last-known-good
    return NextResponse.json({ unavailable: true });
  }
}
