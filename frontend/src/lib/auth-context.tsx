"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { apiFetch, clearTokens, storeTokens } from "./api";

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string;
  is_email_verified: boolean;
  totp_enabled: boolean;
  roles: string[];
}

export type LoginResult = { mfaRequired: false } | { mfaRequired: true; mfaToken: string };

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  verifyMfa: (mfaToken: string, code: string) => Promise<void>;
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
    // POST /auth/login returns either a normal token pair, or — if the
    // account has TOTP 2FA enabled — an MFA challenge (mfa_required: true,
    // mfa_token) instead. Password was already correct at that point; the
    // caller needs to collect a 6-digit code and call verifyMfa() next.
    const res = await apiFetch<{
      access_token?: string; refresh_token?: string; mfa_required?: boolean; mfa_token?: string;
    }>("/auth/login", { method: "POST", auth: false, body: JSON.stringify({ email, password }) });

    if (res.mfa_required && res.mfa_token) {
      return { mfaRequired: true, mfaToken: res.mfa_token };
    }
    storeTokens(res.access_token!, res.refresh_token!);
    await refreshUser();
    return { mfaRequired: false };
  };

  const verifyMfa = async (mfaToken: string, code: string) => {
    const tokens = await apiFetch<{ access_token: string; refresh_token: string }>("/auth/2fa/verify-login", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ mfa_token: mfaToken, code }),
    });
    storeTokens(tokens.access_token, tokens.refresh_token);
    await refreshUser();
  };

  const logout = async () => {
    const refresh = window.localStorage.getItem("ss_refresh_token");
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
