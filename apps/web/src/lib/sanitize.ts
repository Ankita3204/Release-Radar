import DOMPurify from "isomorphic-dompurify";

// The ONLY sanctioned way to turn untrusted strings into HTML. Today the UI renders everything as text,
// so nothing calls htmlFrom(); it exists so a future "render markdown" feature has one reviewed gate.
export function htmlFrom(untrusted: string): string {
  return DOMPurify.sanitize(untrusted, { ALLOWED_TAGS: ["b", "i", "em", "strong", "code", "pre", "br", "p", "ul", "ol", "li"], ALLOWED_ATTR: [] });
}

// For build logs shown in <pre>: strip ANSI/control characters, keep it text.
export function plainLog(raw: string, max = 20_000): string {
  // eslint-disable-next-line no-control-regex
  return raw.replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, "").replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, "").slice(0, max);
}

// Only https://github.com/... links are ever put in an href (defence in depth; the API already filters).
export function safeGithubUrl(url: string | null): string | undefined {
  return url && url.startsWith("https://github.com/") ? url : undefined;
}
