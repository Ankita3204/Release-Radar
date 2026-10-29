import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { AlertManager } from "@/features/alerts/alert-manager";
import { AlertChannel, Me } from "@/lib/schemas";
import { serverGet } from "@/lib/server-api";
import { z } from "zod";

export const metadata: Metadata = { title: "Alerts" };

export default async function AlertsPage() {
  const me = await serverGet("/v1/me", Me);
  if (me.role === "viewer") redirect("/dashboard"); // UI nicety only; the API enforces the role
  const channels = await serverGet("/v1/alerts", z.array(AlertChannel));
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Alerts</h1>
      <AlertManager channels={channels} csrf={me.csrf_token} />
    </div>
  );
}
