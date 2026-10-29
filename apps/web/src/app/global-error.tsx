"use client";

import "./globals.css";

// Last resort: replaces the root layout, so it must render its own <html> and <body>.
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body>
        <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-4 px-6">
          <h1 className="text-3xl font-bold tracking-tight">ReleaseRadar hit an unexpected error</h1>
          <p className="text-muted">Reload the page. If it keeps happening, check the server logs.</p>
          {error.digest && <p className="font-board text-xs text-muted">Reference: {error.digest}</p>}
          <button type="button" onClick={() => reset()} className="w-fit rounded-sm bg-ink px-4 py-2 text-sm font-semibold text-panel hover:bg-rail">
            Reload
          </button>
        </main>
      </body>
    </html>
  );
}
