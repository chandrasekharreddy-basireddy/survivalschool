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

/** Default per-request timeout. Uploads override this via options.timeoutMs
 * because multipart bodies legitimately take longer. Without a timeout a slow
 * or wedged backend leaves the UI stuck on a loading state that never
 * resolves. */
const DEFAULT_TIMEOUT_MS = 30_000;

/** Sends the user to the login screen when their session can no longer be
 * refreshed. Kept here (rather than in every caller) so a hard expiry always
 * ends the same way instead of leaving a protected page half-broken. Guards
 * against redirect loops if we're already on /login. */
function redirectToLogin() {
  if (typeof window === "undefined") return;
  clearTokens();
  const { pathname, search } = window.location;
  if (pathname.startsWith("/login")) return;
  const next = encodeURIComponent(pathname + search);
  window.location.assign(`/login?next=${next}&reason=session_expired`);
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit & { auth?: boolean; timeoutMs?: number } = {}
): Promise<T> {
  const { auth = true, headers, timeoutMs = DEFAULT_TIMEOUT_MS, ...rest } = options;
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

    // Abort the request if it outlives the timeout, while still respecting any
    // signal the caller passed (we abort our controller when theirs fires).
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const callerSignal = rest.signal as AbortSignal | null | undefined;
    if (callerSignal) {
      if (callerSignal.aborted) controller.abort();
      else callerSignal.addEventListener("abort", () => controller.abort(), { once: true });
    }
    try {
      return await fetch(`${API_BASE}${path}`, { ...rest, headers: finalHeaders, signal: controller.signal });
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError" && !callerSignal?.aborted) {
        throw new ApiError("The request timed out. Please try again.", "request_timeout", 0);
      }
      throw new ApiError("Network error. Please check your connection and try again.", "network_error", 0);
    } finally {
      clearTimeout(timer);
    }
  };

  let resp = await doFetch();

  if (resp.status === 401 && auth) {
    // A visitor who was never signed in has no refresh token to begin with —
    // that's just an ordinary anonymous 401 (e.g. AuthProvider's own /auth/me
    // probe on every page), not a session expiry, and must not force-navigate
    // whatever public page they're on to /login. Only a *rejected* refresh
    // token means a real session actually ended.
    const hadRefreshToken = !!getStoredTokens().refresh;
    const newAccess = await tryRefresh();
    if (newAccess) {
      resp = await doFetch(newAccess);
    } else if (hadRefreshToken) {
      // Refresh token is gone or rejected — the session is truly over. Send the
      // user to login rather than leaving them on a protected page whose data
      // fetches all 401.
      redirectToLogin();
      throw new ApiError("Your session has expired. Please log in again.", "session_expired", 401);
    }
    // else: fall through to the generic !resp.ok handling below, which parses
    // the body and throws a plain ApiError without touching navigation.
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
