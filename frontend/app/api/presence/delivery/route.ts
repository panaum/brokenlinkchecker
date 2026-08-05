import { NextRequest, NextResponse } from "next/server";
import { handoffUrl } from "@/lib/handoff-contract";
import { deliveryPresence, presenceEnabled, type PresenceDeliverable } from "@/lib/presence-shape";

// PRESENCE (Seam 3) — delivery presence for one site: how many deliverables are
// in QA right now and who has them. Sibling of /api/delivery on purpose: same
// upstream producer, but its own 60s freshness window (the Delivery panel's
// 15-min cache is right for a detail card and wrong for an awareness line), so
// /api/delivery and DeliveryPanel are untouched in both flag states.
//
// Read-only. The bridge key stays server-side; handoff links are signed here.
// Staleness over errors (constitution rule 6): unreachable → last-known-good,
// or a quiet empty answer. Never a 5xx — the Overview must not care.

const CACHE_MS = 60 * 1000;
const TIMEOUT_MS = 4000;

type Cached = { deliverables: PresenceDeliverable[]; as_of: string; at: number };
const cache = new Map<string, Cached>();

// The one shape this route ever returns. `enabled:false` and `count:0` both
// mean "render nothing" to the client.
const QUIET = { enabled: true, count: 0, testers: [], open_in_qa_url: null, stale: false };

export async function GET(req: NextRequest) {
  if (!presenceEnabled(process.env)) {
    return NextResponse.json({ enabled: false });
  }

  const siteId = req.nextUrl.searchParams.get("site_id");
  if (!siteId) return NextResponse.json({ error: "site_id required" }, { status: 400 });

  const base = (process.env.DASHBOARD_BRIDGE_URL || "").replace(/\/$/, "");
  const key = process.env.DASHBOARD_BRIDGE_KEY || "";
  if (!base || !key) return NextResponse.json(QUIET);

  const hit = cache.get(siteId);
  if (hit && Date.now() - hit.at < CACHE_MS) return NextResponse.json(shape(hit, false));

  try {
    const res = await fetch(
      `${base}/api/registry-bridge/delivery?registry_site_id=${encodeURIComponent(siteId)}`,
      {
        headers: { Authorization: `Bearer ${key}` },
        signal: AbortSignal.timeout(TIMEOUT_MS),
        cache: "no-store",
      },
    );
    if (!res.ok) throw new Error(`http ${res.status}`);
    const data = (await res.json()) as { deliverables?: PresenceDeliverable[]; as_of?: string };
    const fresh: Cached = {
      deliverables: data.deliverables ?? [],
      as_of: data.as_of ?? new Date().toISOString(),
      at: Date.now(),
    };
    cache.set(siteId, fresh);
    return NextResponse.json(shape(fresh, false));
  } catch {
    // Last-known-good if we have it; otherwise say nothing at all rather than
    // put an error box on a page that has nothing to do with the Dashboard.
    return NextResponse.json(hit ? shape(hit, true) : QUIET);
  }
}

function shape(c: Cached, stale: boolean) {
  const p = deliveryPresence(c.deliverables);
  const dashApp = (process.env.DASHBOARD_APP_URL || "").replace(/\/$/, "");
  const secret = process.env.SPINE_SECRET || "";
  return {
    enabled: true,
    count: p.count,
    testers: p.testers,
    as_of: c.as_of,
    stale,
    // Signed SERVER-SIDE, short-lived (≤300s). Null when the handoff isn't
    // configured — the line then renders as plain text, not a dead link.
    open_in_qa_url:
      p.client_path && dashApp && secret
        ? handoffUrl(dashApp, p.client_path, secret, Math.floor(Date.now() / 1000))
        : null,
  };
}
