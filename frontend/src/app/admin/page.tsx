"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";

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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<DashboardStats>("/admin/dashboard").then(setStats).catch((e) => setError(e.message));
  }, [user]);

  if (loading) return <div className="mx-auto max-w-6xl px-6 py-16 text-slate-400">Loading…</div>;
  if (!user || !user.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r))) {
    return <div className="mx-auto max-w-6xl px-6 py-16 text-slate-400">You don&apos;t have access to the admin console.</div>;
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-2xl font-bold text-white">Admin console</h1>
      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}
      {stats && (
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {TILES.map((t) => (
            <div key={t.key} className="card">
              <p className="text-xs uppercase tracking-wide text-slate-500">{t.label}</p>
              <p className="mt-2 text-3xl font-bold text-white">{stats[t.key]}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
