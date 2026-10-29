"use client";

import Link from "next/link";
import { useEffect } from "react";
import { Button, buttonClass } from "@/components/ui/button";
import { ErrorPanel } from "@/components/ui/error-panel";

// Shared body for every error.tsx. In production Next hides the real message from the browser on purpose
// (it would leak server details), so this shows a safe generic explanation plus the digest to grep in server logs.
export function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="px-6 py-16">
      <ErrorPanel
        title="Something went wrong"
        digest={error.digest}
        actions={
          <>
            <Button onClick={() => reset()}>Try again</Button>
            <Link href="/login" className={buttonClass("outline")}>Back to sign in</Link>
          </>
        }
      >
        <p>This page couldn&rsquo;t load. The most common cause is the API being unreachable or misconfigured.</p>
      </ErrorPanel>
    </div>
  );
}
