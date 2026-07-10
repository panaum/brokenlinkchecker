import { NextRequest } from "next/server";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// Run ONE opted-in form's active test — a single real submission. The backend
// refuses unless the global flag is on AND this form is opted in.
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ site_id: string }> },
) {
  const { site_id } = await params;
  const body = await req.json().catch(() => ({}));
  const qs = new URLSearchParams({
    form_key: String(body.form_key ?? ""),
    form_selector: String(body.form_selector ?? ""),
  });
  try {
    const res = await fetch(
      `${backend()}/api/sites/${site_id}/forms/active-test?${qs.toString()}`,
      { method: "POST", cache: "no-store" },
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
