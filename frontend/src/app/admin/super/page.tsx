"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";
import { PageLoader } from "@/components/PageLoader";

interface UserOut {
  id: string;
  email: string;
  full_name: string;
  is_email_verified: boolean;
  is_active: boolean;
  roles: string[];
}

export default function SuperAdminPage() {
  const { user, loading } = useAuth();
  const [elevated, setElevated] = useState<UserOut[] | null>(null);

  useEffect(() => {
    if (!user || !user.roles.includes("SUPER_ADMIN")) return;
    // No dedicated "list elevated accounts" endpoint exists — this reuses
    // the same admin user-search endpoint /admin/users already uses, at a
    // high limit, and filters client-side. Admin-tier accounts are a small,
    // bounded set at any real institution, so this is cheap in practice;
    // if that stops being true, this should become a real server-side
    // filter instead of pulling every user to filter here.
    apiFetch<UserOut[]>("/admin/users?limit=200")
      .then((rows) => setElevated(rows.filter((u) => u.roles.includes("ADMIN") || u.roles.includes("SUPER_ADMIN"))))
      .catch(() => setElevated([]));
  }, [user]);

  if (loading) return <div className="mx-auto max-w-4xl px-6 py-16 text-fg-muted"><PageLoader size="md" /></div>;
  if (!user || !user.roles.includes("SUPER_ADMIN")) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">This area is for super admins.</p>
        <Link href="/dashboard" className="btn-secondary mt-6 inline-flex">Back to dashboard</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-fg">Super Admin</h1>
        <Link href="/admin" className="text-sm text-brand-600 dark:text-brand-400 hover:underline">Admin console &rarr;</Link>
      </div>
      <p className="mt-1 text-sm text-fg-muted">
        The handful of controls only a Super Admin can use — everything else lives in the regular Admin console.
      </p>

      <div className="card mt-6">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-fg">Elevated accounts</h2>
          <Link href="/admin/users" className="text-sm text-brand-600 dark:text-brand-400 hover:underline">Manage all users &rarr;</Link>
        </div>
        <p className="mt-1 text-xs text-fg-subtle">
          Everyone currently holding Admin or Super Admin. Assigning or removing either role is a Super-Admin-only
          action, available from the user management table.
        </p>
        {elevated === null ? (
          <p className="mt-4 text-sm text-fg-subtle"><PageLoader size="sm" /></p>
        ) : elevated.length === 0 ? (
          <p className="mt-4 text-sm text-fg-subtle">No elevated accounts found.</p>
        ) : (
          <ul className="mt-3 divide-y divide-ink-800">
            {elevated.map((u) => (
              <li key={u.id} className="flex items-center justify-between py-2.5 text-sm">
                <div>
                  <span className="text-fg">{u.full_name}</span>
                  <span className="ml-2 text-xs text-fg-subtle">{u.email}</span>
                </div>
                <div className="flex gap-1">
                  {u.roles.filter((r) => r === "ADMIN" || r === "SUPER_ADMIN").map((r) => (
                    <span key={r} className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${r === "SUPER_ADMIN" ? "bg-amber-500/10 text-amber-700 dark:text-amber-400" : "bg-ink-800 text-fg-muted"}`}>
                      {r}
                    </span>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card mt-6 border-red-500/30">
        <h2 className="font-semibold text-fg">Danger zone</h2>
        <p className="mt-2 text-sm text-fg-muted">
          <strong className="text-fg">Emergency account reset.</strong> There is a maintenance endpoint —{" "}
          <code className="rounded bg-ink-900 px-1.5 py-0.5 text-xs text-fg-subtle">POST /admin/maintenance/reset-accounts</code>{" "}
          — that permanently deletes every user account and everything referencing one (sessions, attempts,
          certificates, and more). It exists for a total-lockout scenario where no working account is left to sign
          in with, so it&apos;s deliberately <em>not</em> behind a normal login — only a secret header
          (<code className="rounded bg-ink-900 px-1.5 py-0.5 text-xs text-fg-subtle">X-Maintenance-Secret</code>)
          the server operator holds outside the app entirely.
        </p>
        <p className="mt-2 text-sm text-fg-muted">
          There is deliberately no button for this here — it&apos;s irreversible, and clicking something in a web UI is
          the wrong amount of friction for an action this destructive. If you ever need it, call it directly with
          the secret from wherever your deployment&apos;s environment variables are configured.
        </p>
      </div>
    </div>
  );
}
