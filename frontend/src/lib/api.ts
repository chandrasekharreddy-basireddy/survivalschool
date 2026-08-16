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

export function getAccessToken(): string | undefined {
  return getStoredTokens().access;
}

async function tryRefresh(): Promise<string | null> {
  const { refresh } = getStoredTokens();
  if (!refresh) return null;
  const resp = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!resp.ok) return null;
  const data = await resp.json();
  storeTokens(data.access_token, data.refresh_token);
  return data.access_token as string;
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
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(headers as Record<string, string>),
    };
    if (auth && token) finalHeaders["Authorization"] = `Bearer ${token}`;
    return fetch(`${API_BASE}${path}`, { ...rest, headers: finalHeaders });
  };

  let resp = await doFetch();

  if (resp.status === 401 && auth) {
    const newAccess = await tryRefresh();
    if (newAccess) {
      resp = await doFetch(newAccess);
    }
  }

  if (!resp.ok) {
    let body: { error?: { message?: string; code?: string } } = {};
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
