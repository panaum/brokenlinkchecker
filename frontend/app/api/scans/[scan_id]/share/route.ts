import { backendAuthHeaders } from "@/lib/backendToken";
import { NextRequest } from "next/server";

const backend = () => process.env.BACKEND_URL || "http://localhost:8000";

// Mint a public, revocable share link for this scan's report.
export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ scan_id: string }> },
) {
  const { scan_id } = await params;
  try {
    const res = await fetch(`${backend()}/api/scans/${scan_id}/share`, {
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
