import Link from "next/link";
import { buttonClass } from "@/components/ui/button";

// Own 404 page: Next's built-in one uses inline style attributes, which our strict CSP (no 'unsafe-inline') blocks.
export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-4 px-6">
      <p className="font-board text-sm text-muted">404</p>
      <h1 className="text-3xl font-bold tracking-tight">That page doesn&rsquo;t exist</h1>
      <p className="text-muted">The link may be old or mistyped.</p>
      <Link href="/dashboard" className={buttonClass("solid") + " w-fit"}>Go to the deploy board</Link>
    </main>
  );
}
