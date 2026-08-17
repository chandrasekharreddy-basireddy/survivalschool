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

function getStoredTokens(): { access?: string; refresh?: string } {
  if (typeof window === "undefined") return {};
  return {
    access: window.localStorage.getItem("ss_access_token") || undefined,
    refresh: window.localStorage.getItem("ss_refresh_token") || undefined,
  };
}

export function storeTokens(access: string, refresh: string) {
  window.localStorage.setItem("ss_access_token", access);
  window.localStorage.setItem("ss_refresh_token", refresh);
}

export function clearTokens() {
  window.localStorage.removeItem("ss_access_token");
  window.localStorage.removeItem("ss_refresh_token");
}

/** Current access token, for callers that need to hand it to something other
 * than apiFetch — e.g. the WebSocket chat handshake, which must pass the
 * token as a query param since browsers can't set custom headers on a WS
 * upgrade request. */
export function getAccessToken(): string | undefined {
  return getStoredTokens().access;
}

async function tryRefresh(): Promise<string | null> {
  const { refresh } = getStoredTokens();
  if (!refresh) return null;

  try {
    const resp = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!resp.ok) {
      // A refresh token that the server rejects is no longer usable. Remove
      // both credentials so every caller converges on the signed-out state
      // instead of retrying the same dead token on every request.
      clearTokens();
      return null;
    }

    const data = await resp.json();
    if (!data?.access_token || !data?.refresh_token) {
      clearTokens();
      return null;
    }

    storeTokens(data.access_token as string, data.refresh_token as string);
    return data.access_token as string;
  } catch {
    // Network failures are also treated as a failed refresh. The caller will
    // surface the original request error, while stale credentials are removed
    // to avoid a loop of doomed refresh attempts.
    clearTokens();
    return null;
  }
}

// Refresh-token rotation is intentionally single-use on the backend. Without
// a single-flight promise, several simultaneous 401s can all submit the same
// refresh token; only one can win the rotation and the others look like token
// reuse and may revoke the whole session. Sharing one in-flight refresh avoids
// that client-side race and lets every waiting request use the rotated token.
let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = tryRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit & { auth?: boolean } = {}
): Promise<T> {
  const { auth = true, headers, ...rest } = options;
  const isFormData = typeof FormData !== "undefined" && rest.body instanceof FormData;
  const doFetch = async (accessOverride?: string) => {
    const { access } = getStoredTokens();
    const token = accessOverride || access;
    const finalHeaders: Record<string, string> = {
      // FormData bodies (multipart file uploads) must NOT have an explicit
      // Content-Type — the browser sets one itself, including the boundary
      // string, and a hardcoded "application/json" here would corrupt the
      // upload.
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(headers as Record<string, string>),
    };
    if (auth && token) finalHeaders["Authorization"] = `Bearer ${token}`;
    return fetch(`${API_BASE}${path}`, { ...rest, headers: finalHeaders });
  };

  let resp = await doFetch();

  if (resp.status === 401 && auth) {
    const newAccess = await refreshAccessToken();
    if (newAccess) {
      resp = await doFetch(newAccess);
    }
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
