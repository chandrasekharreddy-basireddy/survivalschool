"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";

interface Enrollment { id: string; course_id: string; status: string; percent_complete: number }
interface GamificationStats { total_points: number; current_streak_days: number; longest_streak_days: number; badges: { code: string; name: string; icon: string }[] }
interface Notification { id: string; title: string; body: string; category: string; read_at: string | null; created_at: string }

export default function DashboardPage() {
  const { user, loading } = useAuth();
  const [enrollments, setEnrollments] = useState<Enrollment[] | null>(null);
  const [stats, setStats] = useState<GamificationStats | null>(null);
  const [notifications, setNotifications] = useState<Notification[] | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<Enrollment[]>("/courses/me/enrollments").then(setEnrollments).catch(() => setEnrollments([]));
    apiFetch<GamificationStats>("/gamification/me").then(setStats).catch(() => setStats(null));
    apiFetch<Notification[]>("/notifications?limit=5").then(setNotifications).catch(() => setNotifications([]));
  }, [user]);

  if (loading) return <div className="mx-auto max-w-6xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">You need to sign in to see your dashboard.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  const activeCourses = (enrollments || []).filter((e) => e.status === "active");
  const completedCourses = (enrollments || []).filter((e) => e.status === "completed");

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Welcome back, {user.full_name.split(" ")[0]}.</h1>
      {!user.is_email_verified && (
        <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
          Verify your email to unlock enrollment, quizzes, and exams. Check your inbox for the link.
        </div>
      )}

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <div className="card">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-fg">Continue learning</h2>
              <Link href="/courses" className="text-sm text-brand-400 hover:underline">Browse courses</Link>
            </div>
            {enrollments === null ? (
              <p className="mt-4 text-sm text-fg-subtle">Loading…</p>
            ) : activeCourses.length === 0 ? (
              <div className="mt-6 rounded-lg border border-dashed border-ink-700 p-8 text-center text-sm text-fg-subtle">
                No active courses yet. <Link href="/courses" className="text-brand-400 hover:underline">Enroll in your first course</Link> to get started.
              </div>
            ) : (
              <ul className="mt-4 space-y-3">
                {activeCourses.map((e) => (
                  <li key={e.id} className="flex items-center justify-between rounded-lg border border-ink-700 px-4 py-3">
                    <div className="flex-1">
                      <div className="mb-1 h-2 w-full overflow-hidden rounded-full bg-ink-800">
                        <div className="h-full rounded-full bg-brand-500" style={{ width: `${e.percent_complete}%` }} />
                      </div>
                      <span className="text-xs text-fg-subtle">{e.percent_complete}% complete</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="card">
            <h2 className="font-semibold text-fg">Recent notifications</h2>
            {notifications === null ? (
              <p className="mt-4 text-sm text-fg-subtle">Loading…</p>
            ) : notifications.length === 0 ? (
              <p className="mt-4 text-sm text-fg-subtle">You&apos;re all caught up.</p>
            ) : (
              <ul className="mt-4 space-y-3">
                {notifications.map((n) => (
                  <li key={n.id} className="border-b border-ink-800 pb-3 last:border-0 last:pb-0">
                    <p className="text-sm font-medium text-fg">{n.title}</p>
                    <p className="text-xs text-fg-subtle">{n.body}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="card">
            <h2 className="font-semibold text-fg">Your progress</h2>
            {stats === null ? (
              <p className="mt-4 text-sm text-fg-subtle">Loading…</p>
            ) : (
              <>
                <div className="mt-4 grid grid-cols-2 gap-4 text-center">
                  <div>
                    <div className="text-2xl font-bold text-brand-400">{stats.total_points}</div>
                    <div className="text-xs text-fg-subtle">points</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-brand-400">{stats.current_streak_days}</div>
                    <div className="text-xs text-fg-subtle">day streak</div>
                  </div>
                </div>
                {stats.badges.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {stats.badges.map((b) => (
                      <span key={b.code} className="rounded-full bg-brand-500/10 px-3 py-1 text-xs text-brand-300">
                        {b.name}
                      </span>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>

          <div className="card">
            <h2 className="font-semibold text-fg">Certificates earned</h2>
            <p className="mt-2 text-sm text-fg-subtle">{completedCourses.length} course{completedCourses.length === 1 ? "" : "s"} completed</p>
          </div>
        </div>
      </div>
    </div>
  );
}
