"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError, apiSend } from "@/lib/api-client";
import type { AlertChannel } from "@/lib/schemas";

const HINT = { slack: "https://hooks.slack.com/services/…", discord: "https://discord.com/api/webhooks/…" } as const;

export function AlertManager({ channels, csrf }: { channels: AlertChannel[]; csrf: string }) {
  const router = useRouter();
  const [kind, setKind] = useState<"slack" | "discord">("slack");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function add() {
    setBusy(true);
    setError(null);
    try {
      await apiSend("/v1/alerts", "POST", csrf, { kind, url });
      setUrl(""); // the secret never lingers in component state
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError && e.status === 422 ? `That isn't a valid ${kind === "slack" ? "Slack" : "Discord"} webhook address.` : "Couldn't save the channel. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    try {
      await apiSend(`/v1/alerts/${id}`, "DELETE", csrf);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      <section aria-labelledby="channels" className="space-y-3">
        <h2 id="channels" className="text-xl font-bold tracking-tight">Where failures go</h2>
        {channels.length === 0 ? (
          <p className="border border-dashed border-rule bg-panel p-6 text-muted">No channels yet. Add one below to get a message when a build or deploy fails.</p>
        ) : (
          <ul className="divide-y divide-rule border border-ink bg-panel">
            {channels.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-4 px-4 py-3">
                <span><span className="font-semibold">{c.kind === "slack" ? "Slack" : "Discord"}</span> <span className="font-board text-xs text-muted">ending …{c.url_last4}</span></span>
                <Button variant="danger" disabled={busy} onClick={() => remove(c.id)}>Remove</Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="add" className="space-y-3">
        <h2 id="add" className="text-xl font-bold tracking-tight">Add a channel</h2>
        <div className="grid max-w-xl gap-4">
          <label className="grid gap-1 text-sm font-semibold">
            Service
            <select className="rounded-sm border border-ink/50 bg-panel px-3 py-2 font-normal" value={kind} onChange={(e) => setKind(e.target.value as "slack" | "discord")}>
              <option value="slack">Slack</option>
              <option value="discord">Discord</option>
            </select>
          </label>
          <label className="grid gap-1 text-sm font-semibold">
            Webhook address
            <input className="rounded-sm border border-ink/50 bg-panel px-3 py-2 font-board text-sm font-normal" type="password" autoComplete="off" spellCheck={false} placeholder={HINT[kind]} value={url} onChange={(e) => setUrl(e.target.value)} />
            <span className="text-xs font-normal text-muted">Stored encrypted. After saving, only the last four characters are shown.</span>
          </label>
          {error && <p role="alert" className="text-sm font-semibold text-stop">{error}</p>}
          <Button className="w-fit" disabled={busy || url.length < 20} onClick={add}>Save channel</Button>
        </div>
      </section>
    </div>
  );
}
