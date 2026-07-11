import { NextRequest } from "next/server";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// Revoke a share link. The public URL 404s afterwards.
export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ token: string }> },
) {
  const { token } = await params;
  try {
    const res = await fetch(`${backend()}/api/share/${token}`, {
      method: "DELETE",
      cache: "no-store",
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
