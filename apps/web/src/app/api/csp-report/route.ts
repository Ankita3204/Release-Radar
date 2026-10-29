import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

// Receives CSP violation reports. Size-capped, logged as text only, never reflected.
export async function POST(req: NextRequest) {
  const text = (await req.text()).slice(0, 2048).replace(/[\r\n]+/g, " ");
  console.warn(JSON.stringify({ event: "csp_violation", report: text }));
  return new Response(null, { status: 204 });
}
