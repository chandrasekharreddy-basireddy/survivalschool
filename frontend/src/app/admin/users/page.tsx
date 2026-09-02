"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { PageLoader } from "@/components/PageLoader";

interface UserOut {
  id: string;
  email: string;
  full_name: string;
  is_email_verified: boolean;
  is_active: boolean;
  roles: string[];
}

const ASSIGNABLE_ROLES = ["STUDENT", "INSTRUCTOR", "MODERATOR", "SUPPORT", "ADMIN"];

export default function AdminUsersPage() {
  const { user, loading } = useAuth();
  const toast = useToast();
  const [users, setUsers] = useState<UserOut[] | null>(null);
  const [q, setQ] = useState("");

  const load = () => {
    apiFetch<UserOut[]>(`/admin/users?limit=100${q ? `&q=${encodeURIComponent(q)}` : ""}`)
      .then(setUsers)
      .catch(() => setUsers([]));
  };

  useEffect(() => {
    if (user) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const toggleActive = async (target: UserOut) => {
    if (target.is_active && !window.confirm(`Deactivate ${target.full_name}? They'll immediately lose access.`)) return;
    try {
      const updated = await apiFetch<UserOut>(`/admin/users/${target.id}/${target.is_active ? "deactivate" : "activate"}`, { method: "POST" });
      setUsers((prev) => prev && prev.map((u) => (u.id === target.id ? updated : u)));
      toast.show(target.is_active ? "User deactivated." : "User reactivated.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't update this user.", "error");
    }
  };

  const assignRole = async (target: UserOut, role: string) => {
    try {
      const updated = await apiFetch<UserOut>(`/users/${target.id}/roles/${role}`, { method: "POST" });
      setUsers((prev) => prev && prev.map((u) => (u.id === target.id ? updated : u)));
      toast.show(`${role} role assigned.`, "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't assign that role.", "error");
    }
  };

  if (loading) return <div className="mx-auto max-w-5xl px-6 py-16 text-fg-muted"><PageLoader size="md" /></div>;
  if (!user || !user.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r))) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">This area is for admins.</p>
        <Link href="/dashboard" className="btn-secondary mt-6 inline-flex">Back to dashboard</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-fg">User management</h1>
        <Link href="/admin/audit-logs" className="text-sm text-brand-600 dark:text-brand-400 hover:underline">Audit logs &rarr;</Link>
      </div>

      <div className="mt-4 flex gap-3">
        <input className="input" placeholder="Search by name or email" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} />
        <button onClick={load} className="btn-secondary shrink-0">Search</button>
      </div>

      <div className="card mt-6 overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-ink-800 text-left text-xs uppercase tracking-wide text-fg-subtle">
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Roles</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {(users || []).map((u) => (
              <tr key={u.id} className="border-b border-ink-800 last:border-0">
                <td className="px-4 py-3 text-fg">{u.full_name}</td>
                <td className="px-4 py-3 text-fg-muted">{u.email}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {u.roles.map((r) => (
                      <span key={r} className="rounded bg-ink-800 px-1.5 py-0.5 text-[11px] text-fg-muted">{r}</span>
                    ))}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className={u.is_active ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}>{u.is_active ? "Active" : "Deactivated"}</span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <select
                      className="input !w-auto !py-1 text-xs"
                      defaultValue=""
                      onChange={(e) => { if (e.target.value) { assignRole(u, e.target.value); e.target.value = ""; } }}
                    >
                      <option value="" disabled>+ role</option>
                      {ASSIGNABLE_ROLES.filter((r) => !u.roles.includes(r)).map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                    <button onClick={() => toggleActive(u)} className="btn-secondary !px-2 !py-1 text-xs">
                      {u.is_active ? "Deactivate" : "Activate"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users !== null && users.length === 0 && <p className="p-6 text-center text-sm text-fg-subtle">No users found.</p>}
      </div>
    </div>
  );
}
