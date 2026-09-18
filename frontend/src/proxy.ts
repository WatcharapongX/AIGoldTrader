import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Public routes that do not require authentication.
 * All other routes redirect to /login if no refresh cookie is present.
 *
 * NOTE: Refresh cookie presence (__Host-aigold_refresh or aigold_refresh_dev)
 * is an optimistic navigation hint only. It does not replace or constitute
 * authorization; actual token verification and authorization happen
 * server-side on every FastAPI endpoint.
 */
const PUBLIC_PATHS = ["/login"];
// Also allow unauthenticated requests from image optimization for this asset.
const PUBLIC_ASSETS = new Set(["/images/login-bg.jpg"]);

/** Paths that should be excluded from middleware entirely. */
const EXCLUDED_PREFIXES = ["/_next", "/favicon.ico", "/api"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip Next.js internals and static assets
  if (PUBLIC_ASSETS.has(pathname) || EXCLUDED_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return NextResponse.next();
  }

  const hasToken =
    request.cookies.get("__Host-aigold_refresh")?.value ||
    request.cookies.get("aigold_refresh_dev")?.value;

  const isPublicPath = PUBLIC_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + "/"),
  );

  // Unauthenticated user trying to access protected route → redirect to login
  if (!hasToken && !isPublicPath) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname + (request.nextUrl.search || ""));
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
