import { z } from "zod";

// API responses are validated too: the frontend treats the network as untrusted.
export const Me = z.object({ login: z.string(), avatar_url: z.string().nullable(), role: z.enum(["owner", "admin", "viewer"]), csrf_token: z.string() });
export const Build = z.object({
  id: z.string().uuid(), repo: z.string(), kind: z.enum(["build", "deploy"]), workflow: z.string().nullable(), branch: z.string().nullable(),
  head_sha: z.string().nullable(), status: z.string(), conclusion: z.string().nullable(), html_url: z.string().nullable(), updated_at: z.string(),
});
export const Dora = z.object({
  window_days: z.number(), deployments: z.number(), deployment_frequency_per_day: z.number().nullable(),
  change_failure_rate: z.number().nullable(), mttr_seconds: z.number().nullable(),
});
export const AlertChannel = z.object({ id: z.string().uuid(), kind: z.enum(["slack", "discord"]), url_last4: z.string(), created_at: z.string() });

export type Me = z.infer<typeof Me>;
export type Build = z.infer<typeof Build>;
export type Dora = z.infer<typeof Dora>;
export type AlertChannel = z.infer<typeof AlertChannel>;
