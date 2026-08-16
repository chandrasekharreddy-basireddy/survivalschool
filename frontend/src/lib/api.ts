"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(message: string, code: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

// Browser authentication is cookie-based. Tokens are intentionally never
// persisted to localStorage/sessionStorage or exposed as JS-readable state.
export function storeTokens(_access: string, _refresh: string) {
  // Legacy no-op retained for callers during the cookie-auth migration.
}

export function clearTokens() {
  // Server-side /auth/logout clears HttpOnly cookies. No browser storage is used.
}

export function getAccessToken(): string | undefined {
  // WebSockets authenticate from the HttpOnly cookie; JavaScript does not
  // receive the access token anymore.
  return undefined;
}

async function tryRefresh(): Promise<boolean> {
  const resp = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Auth-Mode": "cookie",
    },
    credentials: "include",
    body: JSON.stringify({}),
  });
  return resp.ok;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit & { auth?: boolean } = {}
): Promise<T> {
  const { auth = true, headers, ...rest } = options;
  const isFormData = typeof FormData !== "undefined" && rest.body instanceof FormData;
  const finalHeaders: Record<string, string> = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    "X-Auth-Mode": "cookie",
    ...(headers as Record<string, string>),
  };
  const doFetch = () => fetch(`${API_BASE}${path}`, {
    ...rest,
    credentials: "include",
    headers: finalHeaders,
  });

  let resp = await doFetch();

  if (resp.status === 401 && auth) {
    const refreshed = await tryRefresh();
    if (refreshed) resp = await doFetch();
  }

  if (!resp.ok) {
    let body: any = {};
    try {
      body = await resp.json();
    } catch {
      /* ignore */
    }
    const err = body?.error || {};
    throw new ApiError(err.message || resp.statusText, err.code || "unknown_error", resp.status);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}
