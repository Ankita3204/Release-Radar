import { Lamp, toneFor } from "@/components/ui/status";
import { safeGithubUrl } from "@/lib/sanitize";
import type { Build } from "@/lib/schemas";

const fmt = new Intl.DateTimeFormat("en", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });

// Everything below is rendered as text nodes. React escapes it; no HTML from CI data is ever injected.
export function BuildBoard({ builds }: { builds: Build[] }) {
  if (builds.length === 0) {
    return (
      <div className="border border-dashed border-rule bg-panel p-8">
        <p className="font-semibold">No builds yet.</p>
        <p className="mt-1 text-muted">Install the ReleaseRadar GitHub App on a repository and push a commit. Runs appear here within seconds.</p>
      </div>
    );
  }
  return (
    <div className="overflow-x-auto border border-ink bg-panel">
      <table className="w-full min-w-[640px] text-left text-sm">
        <caption className="sr-only">Most recent builds and deployments</caption>
        <thead className="border-b border-ink bg-ink text-panel">
          <tr>
            <th scope="col" className="px-4 py-2 font-semibold">Status</th>
            <th scope="col" className="px-4 py-2 font-semibold">Repository</th>
            <th scope="col" className="px-4 py-2 font-semibold">What ran</th>
            <th scope="col" className="px-4 py-2 font-semibold">Commit</th>
            <th scope="col" className="px-4 py-2 font-semibold">UTC</th>
          </tr>
        </thead>
        <tbody>
          {builds.map((b) => {
            const { tone, label } = toneFor(b.status, b.conclusion);
            const href = safeGithubUrl(b.html_url);
            return (
              <tr key={b.id} className="border-b border-rule last:border-0">
                <td className="whitespace-nowrap px-4 py-3"><Lamp tone={tone} label={label} /></td>
                <td className="px-4 py-3 font-semibold">{b.repo}</td>
                <td className="px-4 py-3">
                  <span className="block">{b.kind === "deploy" ? "Deploy to " : ""}{b.workflow ?? "unnamed"}</span>
                  <span className="block font-board text-xs text-muted">{b.branch ?? "—"}</span>
                </td>
                <td className="px-4 py-3 font-board text-xs">
                  {href ? <a className="text-rail underline" href={href} target="_blank" rel="noopener noreferrer">{b.head_sha?.slice(0, 7) ?? "open"}</a> : (b.head_sha?.slice(0, 7) ?? "—")}
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-board text-xs text-muted">{fmt.format(new Date(b.updated_at))}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
