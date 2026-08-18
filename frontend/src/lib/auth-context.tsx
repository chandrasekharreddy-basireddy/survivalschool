"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { apiFetch, clearTokens, storeTokens } from "./api";
import { unsubscribeFromPush } from "./push";

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string;
  is_email_verified: boolean;
  totp_enabled: boolean;
  roles: string[];
}

export type LoginResult = { mfaRequired: false; user: CurrentUser } | { mfaRequired: true; mfaToken: string };

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  verifyMfa: (mfaToken: string, code: string) => Promise<CurrentUser>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = async () => {
    try {
      const me = await apiFetch<CurrentUser>("/auth/me");
      setUser(me);
    } catch {
      setUser(null);
    }
  };

  useEffect(() => {
    refreshUser().finally(() => setLoading(false));
  }, []);

  const login = async (email: string, password: string): Promise<LoginResult> => {
    const res = await apiFetch<{
      access_token?: string; refresh_token?: string; mfa_required?: boolean; mfa_token?: string;
    }>("/auth/login", { method: "POST", auth: false, body: JSON.stringify({ email, password }) });

    if (res.mfa_required && res.mfa_token) {
      return { mfaRequired: true, mfaToken: res.mfa_token };
    }
    storeTokens(res.access_token!, res.refresh_token!);
    const me = await apiFetch<CurrentUser>("/auth/me");
    setUser(me);
    return { mfaRequired: false, user: me };
  };

  const verifyMfa = async (mfaToken: string, code: string): Promise<CurrentUser> => {
    const tokens = await apiFetch<{ access_token: string; refresh_token: string }>("/auth/2fa/verify-login", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ mfa_token: mfaToken, code }),
    });
    storeTokens(tokens.access_token, tokens.refresh_token);
    const me = await apiFetch<CurrentUser>("/auth/me");
    setUser(me);
    return me;
  };

  const logout = async () => {
    const refresh = window.localStorage.getItem("ss_refresh_token");
    // Tear the push subscription down before we drop the tokens: otherwise the
    // browser stays subscribed and the backend keeps its record, so push
    // notifications keep arriving on a device where nobody is logged in — a
    // privacy leak. Best-effort; a failure here must not block sign-out.
    try {
      await unsubscribeFromPush();
    } catch {
      /* best-effort */
    }
    try {
      if (refresh) await apiFetch("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: refresh }) });
    } catch {
      /* best-effort */
    }
    clearTokens();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, verifyMfa, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
