"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";

export function AnalyticsTracker() {
  const pathname = usePathname();
  const { user } = useAuth();

  useEffect(() => {
    if (!user) return;
    apiFetch("/analytics/events", {
      method: "POST",
      body: JSON.stringify({ event_type: "page_view", metadata: { path: pathname } }),
    }).catch(() => {});
  }, [pathname, user]);

  return null;
}
