import { backendAuthHeaders } from "@/lib/backendToken";
import { NextRequest } from "next/server";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// Which forms on this site are enabled for active testing.
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ site_id: string }> },
) {
  const { site_id } = await params;
  try {
    const res = await fetch(`${backend()}/api/sites/${site_id}/forms/optin`, {
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

// Enable/disable active testing for ONE form (deliberate, per-form).
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ site_id: string }> },
) {
  const { site_id } = await params;
  const body = await req.json().catch(() => ({}));
  const qs = new URLSearchParams({
    form_key: String(body.form_key ?? ""),
    enabled: String(Boolean(body.enabled)),
  });
  if (body.test_email) qs.set("test_email", String(body.test_email));
  try {
    const res = await fetch(
      `${backend()}/api/sites/${site_id}/forms/optin?${qs.toString()}`,
      { method: "POST", cache: "no-store", headers: await backendAuthHeaders() },
    );
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
