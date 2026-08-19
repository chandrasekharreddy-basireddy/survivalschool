"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { ApiError, apiFetch } from "@/lib/api";

interface SystemHealth {
  database: boolean;
  redis: boolean;
  status: string;
  app_version: string;
  environment: string;
  uptime_seconds: number;
}

interface DashboardStats {
  total_students: number;
  active_students_7d: number;
  total_courses: number;
  published_courses: number;
  total_enrollments: number;
  certificates_issued: number;
  quiz_attempts_30d: number;
  exam_attempts_30d: number;
}

const TILES: { key: keyof DashboardStats; label: string }[] = [
  { key: "total_students", label: "Total students" },
  { key: "active_students_7d", label: "Active (7d)" },
  { key: "published_courses", label: "Published courses" },
  { key: "total_enrollments", label: "Enrollments" },
  { key: "certificates_issued", label: "Certificates issued" },
  { key: "quiz_attempts_30d", label: "Quiz attempts (30d)" },
  { key: "exam_attempts_30d", label: "Exam attempts (30d)" },
];

export default function AdminDashboardPage() {
  const { user, loading } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<DashboardStats>("/admin/dashboard")
      .then(setStats)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again."));
    apiFetch<SystemHealth>("/admin/system-health").then(setHealth).catch(() => setHealth(null));
  }, [user]);

  if (loading) return <div className="mx-auto max-w-6xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user || !user.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r))) {
    return <div className="mx-auto max-w-6xl px-6 py-16 text-fg-muted">You don&apos;t have access to the admin console.</div>;
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-fg">Admin console</h1>
        <div className="flex gap-4 text-sm">
          <Link href="/admin/users" className="text-brand-600 dark:text-brand-400 hover:underline">Users</Link>
          <Link href="/admin/instructor-applications" className="text-brand-600 dark:text-brand-400 hover:underline">Instructor applications</Link>
          <Link href="/admin/campus-timetable" className="text-brand-600 dark:text-brand-400 hover:underline">Campus timetable</Link>
          <Link href="/admin/audit-logs" className="text-brand-600 dark:text-brand-400 hover:underline">Audit logs</Link>
          <Link href="/admin/certificates" className="text-brand-600 dark:text-brand-400 hover:underline">Certificates</Link>
        </div>
      </div>

      {health && (
        <div className={`mt-4 flex items-center gap-3 rounded-lg border px-4 py-2.5 text-sm ${health.status === "ok" ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-300" : "border-amber-500/30 bg-amber-500/5 text-amber-300"}`}>
          <span className="font-semibold">{health.status === "ok" ? "All systems operational" : "Degraded"}</span>
          <span className="text-fg-subtle">DB {health.database ? "ok" : "down"} &middot; Redis {health.redis ? "ok" : "down"} &middot; v{health.app_version} &middot; {health.environment}</span>
        </div>
      )}

      {error && <p className="mt-4 text-sm text-red-700 dark:text-red-400">{error}</p>}
      {stats && (
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {TILES.map((t) => (
            <div key={t.key} className="card">
              <p className="text-xs uppercase tracking-wide text-fg-subtle">{t.label}</p>
              <p className="mt-2 text-3xl font-bold text-fg">{stats[t.key]}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
