import { NextResponse, type NextRequest } from "next/server";
import { buildCsp } from "@/lib/csp";

const SESSION_COOKIE = "__Host-releaseradar_sid";
const PROTECTED = ["/dashboard", "/settings"];

export function middleware(req: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  const isDev = process.env.NODE_ENV !== "production";
  const csp = buildCsp(nonce, isDev);
  const reportOnly = process.env.CSP_REPORT_ONLY === "1";

  // Cheap gate only: presence of the cookie. The real check (session exists, not expired) happens
  // server-side in the dashboard layout against the API; this just saves a render for anonymous users.
  const { pathname } = req.nextUrl;
  if (PROTECTED.some((p) => pathname === p || pathname.startsWith(p + "/")) && !req.cookies.has(SESSION_COOKIE)) {
    return NextResponse.redirect(new URL("/login", req.url));
  }

  const headers = new Headers(req.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp); // Next reads the nonce from the request CSP and stamps its scripts
  const res = NextResponse.next({ request: { headers } });
  res.headers.set(reportOnly ? "Content-Security-Policy-Report-Only" : "Content-Security-Policy", csp);
  res.headers.set("Cache-Control", "no-store");
  return res;
}

export const config = {
  matcher: [{ source: "/((?!_next/static|_next/image|favicon.ico).*)", missing: [{ type: "header", key: "next-router-prefetch" }] }],
};
