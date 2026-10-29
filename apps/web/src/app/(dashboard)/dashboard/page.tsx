import type { Metadata } from "next";
import { BuildBoard } from "@/features/builds/build-board";
import { Build, Dora } from "@/lib/schemas";
import { serverGet } from "@/lib/server-api";
import { z } from "zod";

export const metadata: Metadata = { title: "Deploy board" };

const pct = (v: number | null) => (v === null ? "No data" : `${(v * 100).toFixed(0)}%`);
const hours = (s: number | null) => (s === null ? "No data" : s < 3600 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);

export default async function DashboardPage() {
  const [builds, dora] = await Promise.all([serverGet("/v1/builds?limit=50", z.array(Build)), serverGet("/v1/metrics/dora?days=30", Dora)]);
  const stats = [
    { label: "Deploys per day", value: dora.deployment_frequency_per_day === null ? "No data" : dora.deployment_frequency_per_day.toFixed(2) },
    { label: "Deploys that failed", value: pct(dora.change_failure_rate) },
    { label: "Time to recover", value: hours(dora.mttr_seconds) },
  ];
  return (
    <div className="space-y-8">
      <section aria-labelledby="dora" className="space-y-3">
        <h1 id="dora" className="text-2xl font-bold tracking-tight">Last {dora.window_days} days</h1>
        <dl className="grid gap-px border border-ink bg-ink sm:grid-cols-3">
          {stats.map((s) => (
            <div key={s.label} className="bg-panel px-5 py-4">
              <dt className="text-sm text-muted">{s.label}</dt>
              <dd className="mt-1 text-2xl font-bold tabular-nums">{s.value}</dd>
            </div>
          ))}
        </dl>
      </section>
      <section aria-labelledby="board" className="space-y-3">
        <h2 id="board" className="text-xl font-bold tracking-tight">Recent runs</h2>
        <BuildBoard builds={builds} />
      </section>
    </div>
  );
}
