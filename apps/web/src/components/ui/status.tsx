import { cn } from "@/lib/utils";

type Tone = "go" | "stop" | "wait" | "idle";

export function toneFor(status: string, conclusion: string | null): { tone: Tone; label: string } {
  if (status !== "completed" && !conclusion) return { tone: "wait", label: status === "queued" ? "Queued" : "Running" };
  if (conclusion === "success") return { tone: "go", label: "Passed" };
  if (conclusion === "failure" || conclusion === "timed_out" || conclusion === "startup_failure") return { tone: "stop", label: conclusion === "timed_out" ? "Timed out" : "Failed" };
  if (conclusion === "cancelled") return { tone: "idle", label: "Cancelled" };
  return { tone: "idle", label: conclusion ? conclusion.replace(/_/g, " ") : "Pending" };
}

// Colour is never the only signal: each tone has its own shape AND a text label.
const shape: Record<Tone, string> = {
  go: "rounded-full bg-go",
  stop: "rotate-45 rounded-[2px] bg-stop",
  wait: "rounded-[2px] bg-wait",
  idle: "rounded-full border-2 border-muted",
};
const text: Record<Tone, string> = { go: "text-go", stop: "text-stop", wait: "text-wait", idle: "text-muted" };

export function Lamp({ tone, label }: { tone: Tone; label: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold", text[tone])}>
      <span aria-hidden className={cn("inline-block h-3 w-3", shape[tone])} />
      {label}
    </span>
  );
}
