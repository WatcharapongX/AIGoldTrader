import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Public routes that do not require authentication.
 * All other routes redirect to /login if no access_token cookie is present.
 *
 * NOTE: We check for the `access_token` cookie set by the client-side auth
 * store. This is a lightweight gate — actual token validation happens
 * server-side on every API call.
 */
const PUBLIC_PATHS = ["/login"];

/** Paths that should be excluded from middleware entirely. */
const EXCLUDED_PREFIXES = ["/_next", "/favicon.ico", "/api"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip Next.js internals and static assets
  if (EXCLUDED_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return NextResponse.next();
  }

  const hasToken =
    request.cookies.get("access_token")?.value ||
    request.headers.get("authorization");

  const isPublicPath = PUBLIC_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + "/"),
  );

  // Unauthenticated user trying to access protected route → redirect to login
  if (!hasToken && !isPublicPath) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // A cookie is only an optimistic hint; allow login to recover expired sessions.
  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico
     */
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
