import Link from "next/link";
import { buttonClass } from "@/components/ui/button";
import { ErrorPanel } from "@/components/ui/error-panel";
import type { UpstreamReason } from "@/lib/server-api";

const COPY: Record<UpstreamReason, { title: string; body: string }> = {
  unreachable: {
    title: "We can't reach the ReleaseRadar API",
    body: "The web app is running, but the API it depends on isn't answering. Check that the API service is up and that API_ORIGIN points to it.",
  },
  timeout: { title: "The API took too long to answer", body: "It didn't respond in time. This is usually temporary, so try again in a moment." },
  forbidden: { title: "You don't have access to this page", body: "Your account's role doesn't allow it. Ask a workspace owner if you think that's wrong." },
  bad_status: { title: "The API ran into a problem", body: "It answered with an error. Try again, and check the API logs if it keeps happening." },
  bad_payload: { title: "The API sent data this app can't read", body: "The web app and API may be on different versions. Redeploy both from the same commit." },
};

export function ApiProblem({ reason }: { reason: UpstreamReason }) {
  const { title, body } = COPY[reason];
  return (
    <div className="px-6 py-16">
      <ErrorPanel
        title={title}
        actions={
          <>
            <Link href="/dashboard" className={buttonClass("solid")}>Try again</Link>
            <Link href="/login" className={buttonClass("outline")}>Back to sign in</Link>
          </>
        }
      >
        <p>{body}</p>
      </ErrorPanel>
    </div>
  );
}
