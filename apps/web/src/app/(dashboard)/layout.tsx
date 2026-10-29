import Link from "next/link";
import { LogoutButton } from "@/features/auth/logout-button";
import { ApiProblem } from "@/components/api-problem";
import { Me } from "@/lib/schemas";
import { serverGet, UpstreamError } from "@/lib/server-api";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  let me: Me;
  try {
    me = await serverGet("/v1/me", Me); // real session validation happens here, on every request
  } catch (e) {
    if (e instanceof UpstreamError) return <ApiProblem reason={e.reason} />; // API down or misbehaving: explain it instead of a blank page
    throw e; // redirects and anything unexpected keep their normal behaviour
  }
  return (
    <div className="mx-auto max-w-6xl px-6 py-6">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-ink pb-4">
        <div className="flex items-baseline gap-8">
          <span className="text-xl font-bold tracking-tight">ReleaseRadar</span>
          <nav aria-label="Main" className="flex gap-6 text-sm font-semibold">
            <Link href="/dashboard" className="hover:text-rail">Deploy board</Link>
            {me.role !== "viewer" && <Link href="/settings/alerts" className="hover:text-rail">Alerts</Link>}
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-muted">{me.login} · {me.role}</span>
          <LogoutButton csrf={me.csrf_token} />
        </div>
      </header>
      <main className="py-8">{children}</main>
    </div>
  );
}
