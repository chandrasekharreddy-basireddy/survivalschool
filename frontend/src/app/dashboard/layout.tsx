"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { getPostLoginPath, isAdmin, isInstructor } from "@/lib/roles";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user && (isAdmin(user) || isInstructor(user))) {
      router.replace(getPostLoginPath(user));
    }
  }, [loading, router, user]);

  if (loading || !user || isAdmin(user) || isInstructor(user)) {
    return <div className="page-frame text-fg-muted">Opening your workspace…</div>;
  }
  return <>{children}</>;
}
