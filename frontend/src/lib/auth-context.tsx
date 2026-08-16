"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { apiFetch } from "./api";

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
    }>("/auth/login", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ email, password }),
    });

    if (res.mfa_required && res.mfa_token) {
      return { mfaRequired: true, mfaToken: res.mfa_token };
    }

    // The backend now sets HttpOnly cookies for browser requests. Never store
    // the bearer tokens in JS-accessible storage.
    const me = await apiFetch<CurrentUser>("/auth/me");
    setUser(me);
    return { mfaRequired: false, user: me };
  };

  const verifyMfa = async (mfaToken: string, code: string): Promise<CurrentUser> => {
    await apiFetch<{ access_token?: string; refresh_token?: string }>("/auth/2fa/verify-login", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ mfa_token: mfaToken, code }),
    });
    const me = await apiFetch<CurrentUser>("/auth/me");
    setUser(me);
    return me;
  };

  const logout = async () => {
    try {
      await apiFetch("/auth/logout", { method: "POST", body: JSON.stringify({}) });
    } catch {
      /* best-effort */
    }
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
