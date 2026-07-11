import { getServerSession } from "next-auth/next";
import { authOptions } from "@/app/api/auth/[...nextauth]/route";
import { mintToken } from "@/lib/backendToken";

// Mint the short-lived HS256 token the backend verifies, from the STAFF NextAuth
// session (the browser forwards it as ?token= on the SSE stream, which can't set
// headers). Clients get the equivalent token from the invite-accept endpoint.
export async function GET() {
  const session = await getServerSession(authOptions);
  const email = session?.user?.email;
  if (!email) {
    return new Response(JSON.stringify({ error: "not signed in" }), {
      status: 401, headers: { "Content-Type": "application/json" },
    });
  }
  const token = mintToken(email);
  if (!token) {
    return new Response(JSON.stringify({ error: "auth not configured" }), {
      status: 500, headers: { "Content-Type": "application/json" },
    });
  }
  return new Response(JSON.stringify({ token }), {
    status: 200,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}
