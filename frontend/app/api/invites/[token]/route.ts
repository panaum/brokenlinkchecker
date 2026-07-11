import { NextRequest } from "next/server";
import { backendAuthHeaders } from "@/lib/backendToken";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// Revoke an invite (agency, member+).
export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ token: string }> },
) {
  const { token } = await params;
  try {
    const res = await fetch(`${backend()}/api/invites/${token}`, {
      method: "DELETE",
      headers: await backendAuthHeaders(),
      cache: "no-store",
    });
    return new Response(await res.text(), {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to reach backend";
    return new Response(JSON.stringify({ error: message }), { status: 500 });
  }
}
