import { NextRequest, NextResponse } from "next/server"
import { getToken } from "next-auth/jwt"

export async function middleware(request: NextRequest) {
  const token = await getToken({
    req: request,
    secret: process.env.NEXTAUTH_SECRET,
  })

  // If user is not authenticated, redirect to login
  if (!token) {
    const loginUrl = new URL("/login", request.url)
    loginUrl.searchParams.set("callbackUrl", request.nextUrl.pathname)
    return NextResponse.redirect(loginUrl)
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    /*
     * Protect the agency app EXCEPT:
     *  - /login
     *  - /api/auth (NextAuth endpoints), /api/slack (Slack webhook)
     *  - Client-facing surfaces, which authenticate via a backend token (not a
     *    NextAuth session) and are gated by the backend, not this wall:
     *      /portal (client home), /reports (the shared report artifact),
     *      and their proxies /api/portal, /api/reports.
     *  - Next.js internals (_next, favicon, etc.)
     */
    "/((?!login|portal|reports|api/auth|api/slack|api/portal|api/reports|_next/static|_next/image|favicon.ico|icon\\.png|opengraph-image\\.png).*)",
  ],
}
