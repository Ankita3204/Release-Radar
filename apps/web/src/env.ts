import "server-only";
import { z } from "zod";

// Validated once at module load; a bad or missing value fails the build/boot instead of running misconfigured.
const schema = z.object({
  API_ORIGIN: z.string().url().refine((u) => !u.endsWith("/"), "no trailing slash"),
  WEB_ORIGIN: z.string().url().refine((u) => !u.endsWith("/"), "no trailing slash"),
  CSP_REPORT_ONLY: z.enum(["0", "1"]).default("0"),
});

const parsed = schema.safeParse(process.env);
if (!parsed.success) {
  throw new Error("Invalid environment: " + parsed.error.issues.map((i) => i.path.join(".")).join(", "));
}
if (process.env.NODE_ENV === "production" && !parsed.data.API_ORIGIN.startsWith("https://")) {
  throw new Error("API_ORIGIN must be https in production");
}
export const env = parsed.data;
