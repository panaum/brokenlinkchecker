import { backendAuthHeaders } from "@/lib/backendToken";
import { NextRequest } from "next/server";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// Generate (or regenerate) this site's report for a period. Agency-only.
export async function POST(req: NextRequest, { params }: { params: Promise<{ site_id: string }> }) {
  const { site_id } = await params;
  const { searchParams } = new URL(req.url);
  const period = searchParams.get("period") || "";
  const qs = period ? `?period=${encodeURIComponent(period)}` : "";
  try {
    const res = await fetch(`${backend()}/api/sites/${site_id}/report/generate${qs}`, {
      method: "POST",
      cache: "no-store",
      headers: await backendAuthHeaders(),
    });
    return new Response(await res.text(), { status: res.status, headers: { "Content-Type": "application/json" } });
  } catch (err) {
    return new Response(JSON.stringify({ error: err instanceof Error ? err.message : "failed" }), { status: 500 });
  }
}
