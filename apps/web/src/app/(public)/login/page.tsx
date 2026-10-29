import { buttonClass } from "@/components/ui/button";

const MESSAGES: Record<string, string> = { oauth: "GitHub sign-in didn't complete. Try again." };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { error } = await searchParams;
  const message = error ? MESSAGES[error] : undefined; // lookup table: the query string is never rendered
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-8 px-6">
      <div className="space-y-3">
        <h1 className="text-4xl font-bold tracking-tight">Every deploy, one board.</h1>
        <p className="max-w-md text-muted">ReleaseRadar reads build and deploy status from your GitHub repositories and tells Slack or Discord the moment one fails.</p>
      </div>
      {message && <p role="alert" className="border-l-4 border-stop bg-panel px-4 py-3 text-stop">{message}</p>}
      <div className="space-y-2">
        {/* Plain anchor on purpose: this is a full-page redirect to GitHub. next/link would prefetch it and start OAuth flows nobody asked for. */}
        {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
        <a href="/api/v1/auth/github/login" className={buttonClass("solid") + " w-fit px-6 py-3"}>Sign in with GitHub</a>
        <p className="text-sm text-muted">Read-only access to Actions and repository metadata. You choose which repositories to install it on.</p>
      </div>
    </main>
  );
}
