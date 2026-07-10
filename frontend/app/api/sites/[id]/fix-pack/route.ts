import { NextRequest } from "next/server";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/app/api/auth/[...nextauth]/route";

export const runtime = "nodejs";

/** Streams the Fix Pack zip from the backend, preserving its filename. */
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return new Response(JSON.stringify({ error: "not signed in" }), { status: 401 });
  }

  const { id } = await params;
  const backend = process.env.BACKEND_URL || "http://localhost:8000";

  try {
    const res = await fetch(`${backend}/api/sites/${id}/fix-pack`, { cache: "no-store" });
    if (!res.ok) {
      return new Response(await res.text(), {
        status: res.status,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(res.body, {
      headers: {
        "Content-Type": "application/zip",
        "Content-Disposition":
          res.headers.get("content-disposition") ??
          'attachment; filename="linkspy-fix-pack.zip"',
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "backend unreachable";
    return new Response(JSON.stringify({ error: message }), { status: 502 });
  }
}
