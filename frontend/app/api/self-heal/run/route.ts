import { backendAuthHeaders } from "@/lib/backendToken";
import { NextRequest } from "next/server";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// Trigger a self-heal run. The backend refuses unless the flag is on AND the
// repo is on the operator allowlist AND a token is configured.
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const qs = new URLSearchParams({
    repo: String(body.repo ?? ""),
    scan_id: String(body.scan_id ?? `ui-${Date.now()}`),
    url: String(body.url ?? ""),
    fix_type: String(body.fix_type ?? "redirect"),
  });
  try {
    const res = await fetch(`${backend()}/api/self-heal/run?${qs.toString()}`, {
      method: "POST",
      cache: "no-store",
      headers: await backendAuthHeaders(),
    });
    const data = await res.json();
    return new Response(JSON.stringify(data), {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to reach backend";
    return new Response(JSON.stringify({ error: message }), { status: 500 });
  }
}
