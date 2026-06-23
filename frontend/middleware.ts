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
     * Protect everything EXCEPT:
     *  - /login
     *  - /api/auth (NextAuth endpoints)
     *  - /api/slack (Slack webhook)
     *  - Next.js internals (_next, favicon, etc.)
     */
    "/((?!login|api/auth|api/slack|_next/static|_next/image|favicon.ico|icon\\.png|opengraph-image\\.png).*)",
  ],
}
