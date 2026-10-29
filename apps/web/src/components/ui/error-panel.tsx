import type { ReactNode } from "react";

// Presentational only (no hooks, no inline styles) so it works in server and client components and under the strict CSP.
export function ErrorPanel({ title, children, actions, digest }: { title: string; children: ReactNode; actions?: ReactNode; digest?: string }) {
  return (
    <div role="alert" className="mx-auto max-w-xl space-y-4 border border-ink border-l-4 border-l-stop bg-panel p-6">
      <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      <div className="space-y-2 text-muted">{children}</div>
      {actions && <div className="flex flex-wrap gap-3 pt-2">{actions}</div>}
      {digest && <p className="font-board text-xs text-muted">Reference: {digest}</p>}
    </div>
  );
}
