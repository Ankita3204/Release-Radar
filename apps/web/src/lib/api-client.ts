"use client";

// Browser -> same-origin BFF proxy (/api/v1/...). The session cookie is HttpOnly, so this code never sees it.
export class ApiError extends Error {
  constructor(public status: number) {
    super(`request failed (${status})`);
  }
}

export async function apiSend(path: string, method: "POST" | "DELETE", csrf: string, body?: unknown): Promise<unknown> {
  const res = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: { "content-type": "application/json", "x-csrf-token": csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(res.status);
  return res.status === 204 ? null : res.json();
}
