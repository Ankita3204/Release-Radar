import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { z } from "zod";
import { env } from "@/env";

export type UpstreamReason = "unreachable" | "timeout" | "forbidden" | "bad_status" | "bad_payload";

// Thrown for every "the API is not behaving" case. Pages can catch it and render a useful message
// instead of letting the render crash into a blank "Application error" screen.
// It carries only a reason code and a status: never an upstream body, URL or header.
export class UpstreamError extends Error {
  constructor(
    public readonly reason: UpstreamReason,
    public readonly status?: number,
  ) {
    super(`upstream ${reason}${status ? ` (${status})` : ""}`);
    this.name = "UpstreamError";
  }
}

// Server-to-server call that forwards the user's session cookie. Never used from client components.
export async function serverGet<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  const jar = await cookies();
  const sid = jar.get("__Host-releaseradar_sid")?.value;
  if (!sid) redirect("/login");

  let res: Response;
  try {
    res = await fetch(env.API_ORIGIN + path, {
      headers: { cookie: `__Host-releaseradar_sid=${encodeURIComponent(sid)}`, accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
  } catch (e) {
    const timedOut = (e as Error | undefined)?.name === "TimeoutError";
    console.error(`[releaseradar] API ${timedOut ? "timed out" : "unreachable"}: GET ${path}`);
    throw new UpstreamError(timedOut ? "timeout" : "unreachable");
  }

  if (res.status === 401) redirect("/login");
  if (res.status === 403) throw new UpstreamError("forbidden", 403);
  if (!res.ok) {
    console.error(`[releaseradar] API returned ${res.status}: GET ${path}`);
    throw new UpstreamError("bad_status", res.status); // generic: no upstream body is surfaced to the page
  }

  const parsed = schema.safeParse(await res.json().catch(() => null));
  if (!parsed.success) {
    console.error(`[releaseradar] API payload did not match the expected schema: GET ${path}`);
    throw new UpstreamError("bad_payload");
  }
  return parsed.data;
}
