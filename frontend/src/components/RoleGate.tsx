"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth-context";
import { getPostLoginPath, hasRole, type AppRole } from "@/lib/roles";

export function RoleGate({ roles, children }: { roles: AppRole[]; children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      return;
    }
    if (!hasRole(user, roles)) router.replace(getPostLoginPath(user));
  }, [loading, user, roles, router]);

  if (loading || !user || !hasRole(user, roles)) {
    return <div className="page-frame text-fg-muted">Checking access…</div>;
  }
  return <>{children}</>;
}
