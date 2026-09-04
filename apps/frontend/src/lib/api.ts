/**
 * Thin fetch wrapper for the backend's /api/v1 surface.
 *
 * Every dashboard page routes errors through ApiError so a 4xx/5xx always
 * surfaces the backend's own `detail` message instead of failing silently.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const API_V1 = `${API_BASE}/api/v1`;

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText || `Request failed with status ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // Response body wasn't JSON (or was empty) — fall back to statusText.
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_V1}${path}`);
  return handle<T>(res);
}

export async function apiPost<T>(
  path: string,
  body: unknown,
  headers?: Record<string, string>
): Promise<T> {
  const res = await fetch(`${API_V1}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  return handle<T>(res);
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_V1}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<T>(res);
}

export async function apiDelete(path: string): Promise<void> {
  const res = await fetch(`${API_V1}${path}`, { method: "DELETE" });
  return handle<void>(res);
}
