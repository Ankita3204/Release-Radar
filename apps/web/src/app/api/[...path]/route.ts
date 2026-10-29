import { NextRequest, NextResponse } from "next/server";
import { env } from "@/env";

// Backend-for-frontend proxy. It is why the API needs no CORS, and why the session cookie can be a
// host-only __Host- cookie on THIS origin. It is intentionally narrow:
//   * only /v1/* on the API, only GET/POST/DELETE
//   * path segments are allow-listed (no "..", no encoded slashes) -> no SSRF/path traversal (CWE-918/22)
//   * only a handful of request/response headers cross the boundary
//   * redirects are NOT followed; they are handed back to the browser
export const dynamic = "force-dynamic";

const METHODS = new Set(["GET", "POST", "DELETE"]);
const SEGMENT = /^[A-Za-z0-9._~-]{1,100}$/;
const REQ_HEADERS = ["cookie", "content-type", "x-csrf-token", "origin", "accept"];
const MAX_BODY = 256 * 1024;

async function handle(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await ctx.params;
  if (!METHODS.has(req.method)) return NextResponse.json({ error: "method_not_allowed" }, { status: 405 });
  if (path[0] !== "v1" || path.length > 6 || !path.every((s) => SEGMENT.test(s) && s !== "." && s !== "..")) {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }

  const target = new URL("/" + path.join("/"), env.API_ORIGIN);
  target.search = req.nextUrl.search;
  if (target.origin !== new URL(env.API_ORIGIN).origin) return NextResponse.json({ error: "not_found" }, { status: 404 });

  const headers = new Headers();
  for (const h of REQ_HEADERS) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  let body: ArrayBuffer | undefined;
  if (req.method !== "GET") {
    body = await req.arrayBuffer();
    if (body.byteLength > MAX_BODY) return NextResponse.json({ error: "payload_too_large" }, { status: 413 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, { method: req.method, headers, body, redirect: "manual", cache: "no-store", signal: AbortSignal.timeout(10_000) });
  } catch {
    return NextResponse.json({ error: "upstream_unavailable" }, { status: 502 });
  }

  const out = new Headers({ "cache-control": "no-store" });
  const ct = upstream.headers.get("content-type");
  if (ct) out.set("content-type", ct);
  const loc = upstream.headers.get("location");
  if (loc) out.set("location", loc);
  for (const c of upstream.headers.getSetCookie()) out.append("set-cookie", c);
  return new Response(upstream.status === 204 || upstream.status === 304 ? null : await upstream.arrayBuffer(), { status: upstream.status, headers: out });
}

export { handle as GET, handle as POST, handle as DELETE };
