"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";

interface Contest { id: string; title: string; starts_at: string; ends_at: string; status: string; question_count: number }
interface Battle { id: string; title: string; status: string; current_round_number: number }
interface Certificate { certificate_number: string }
interface GamificationStats { total_points: number; current_streak_days: number; longest_streak_days: number; badges: { code: string; name: string; icon: string }[] }
interface Notification { id: string; title: string; body: string; category: string; read_at: string | null; created_at: string }
interface DailyChallengeSummary { already_attempted: boolean; my_attempt: { is_correct: boolean; points_awarded: number } | null; current_streak_days: number }

export default function DashboardPage() {
  const { user, loading } = useAuth();
  const [upcomingContests, setUpcomingContests] = useState<Contest[] | null>(null);
  const [battles, setBattles] = useState<Battle[] | null>(null);
  const [certificates, setCertificates] = useState<Certificate[] | null>(null);
  const [stats, setStats] = useState<GamificationStats | null>(null);
  const [notifications, setNotifications] = useState<Notification[] | null>(null);
  const [challenge, setChallenge] = useState<DailyChallengeSummary | null>(null);
  // Distinct from "still loading" (challenge === null) — /daily-challenge/today
  // requires a verified email, so an unverified user's fetch legitimately
  // 403s here; without this the widget got stuck on "Loading…" forever
  // since a caught error and "hasn't resolved yet" were indistinguishable.
  const [challengeUnavailable, setChallengeUnavailable] = useState(false);

  useEffect(() => {
    if (!user) return;
    apiFetch<Contest[]>("/contests/upcoming", { auth: false }).then(setUpcomingContests).catch(() => setUpcomingContests([]));
    apiFetch<Battle[]>("/elimination/battles/me").then(setBattles).catch(() => setBattles([]));
    apiFetch<Certificate[]>("/contests/me/certificates").then(setCertificates).catch(() => setCertificates([]));
    apiFetch<GamificationStats>("/gamification/me").then(setStats).catch(() => setStats(null));
    apiFetch<Notification[]>("/notifications?limit=5").then(setNotifications).catch(() => setNotifications([]));
    apiFetch<DailyChallengeSummary>("/daily-challenge/today")
      .then(setChallenge)
      .catch(() => setChallengeUnavailable(true));
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

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Welcome back, {user.full_name.split(" ")[0]}.</h1>
      {!user.is_email_verified && (
        <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
          Verify your email to unlock contests, elimination battles, and the daily challenge. Check your inbox for the link.
        </div>
      )}

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <div className="card">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-fg">Upcoming contests</h2>
              <Link href="/contests" className="text-sm text-brand-600 dark:text-brand-400 hover:underline">All contests</Link>
            </div>
            {upcomingContests === null ? (
              <p className="mt-4 text-sm text-fg-subtle">Loading…</p>
            ) : upcomingContests.length === 0 ? (
              <div className="mt-6 rounded-lg border border-dashed border-ink-700 p-8 text-center text-sm text-fg-subtle">
                Nothing scheduled right now. <Link href="/contests/ai-weekly/register" className="text-brand-600 underline dark:text-brand-400">Register for the AI Weekly Exam</Link> — it opens every Thursday.
              </div>
            ) : (
              <ul className="mt-4 space-y-3">
                {upcomingContests.map((c) => (
                  <li key={c.id}>
                    <Link href={`/contests/${c.id}`} className="flex items-center justify-between rounded-lg border border-ink-700 px-4 py-3 transition hover:border-brand-500/50">
                      <span className="text-sm font-medium text-fg">{c.title}</span>
                      <span className="text-xs text-fg-subtle">{c.question_count} questions</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="card">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-fg">Elimination battles</h2>
              <Link href="/elimination" className="text-sm text-brand-600 dark:text-brand-400 hover:underline">All battles</Link>
            </div>
            {battles === null ? (
              <p className="mt-4 text-sm text-fg-subtle">Loading…</p>
            ) : battles.length === 0 ? (
              <div className="mt-6 rounded-lg border border-dashed border-ink-700 p-8 text-center text-sm text-fg-subtle">
                No battles yet. <Link href="/elimination" className="text-brand-600 underline dark:text-brand-400">Start one and invite friends</Link>.
              </div>
            ) : (
              <ul className="mt-4 space-y-3">
                {battles.filter((b) => b.status === "lobby" || b.status === "active").slice(0, 5).map((b) => (
                  <li key={b.id}>
                    <Link href={`/elimination/${b.id}`} className="flex items-center justify-between rounded-lg border border-ink-700 px-4 py-3 transition hover:border-brand-500/50">
                      <span className="text-sm font-medium text-fg">{b.title}</span>
                      <span className="text-xs text-fg-subtle">{b.status === "active" ? `round ${b.current_round_number}` : "waiting to start"}</span>
                    </Link>
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
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-fg">Daily challenge</h2>
              <span className="text-xs text-fg-subtle">🔥 {challenge?.current_streak_days ?? stats?.current_streak_days ?? 0}d</span>
            </div>
            {challengeUnavailable ? (
              <p className="mt-3 text-sm text-fg-subtle">Verify your email to unlock the daily challenge.</p>
            ) : challenge === null ? (
              <p className="mt-3 text-sm text-fg-subtle">Loading…</p>
            ) : challenge.already_attempted ? (
              <p className="mt-3 text-sm text-fg-muted">
                {challenge.my_attempt?.is_correct ? `Done for today — you earned ${challenge.my_attempt.points_awarded} points.` : "You've answered today's challenge."}
              </p>
            ) : (
              <p className="mt-3 text-sm text-fg-muted">A new question is waiting — answer it to keep your streak alive.</p>
            )}
            {!challengeUnavailable && (
              <Link href="/daily-challenge" className="btn-primary mt-4 w-full !py-2 text-center text-sm">
                {challenge?.already_attempted ? "View today's challenge" : "Take today's challenge"}
              </Link>
            )}
          </div>

          <div className="card">
            <h2 className="font-semibold text-fg">Your progress</h2>
            {stats === null ? (
              <p className="mt-4 text-sm text-fg-subtle">Loading…</p>
            ) : (
              <>
                <div className="mt-4 grid grid-cols-2 gap-4 text-center">
                  <div>
                    <div className="text-2xl font-bold text-brand-600 dark:text-brand-400">{stats.total_points}</div>
                    <div className="text-xs text-fg-subtle">points</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-brand-600 dark:text-brand-400">{stats.current_streak_days}</div>
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
            <p className="mt-2 text-sm text-fg-subtle">{certificates === null ? "…" : certificates.length} certificate{certificates?.length === 1 ? "" : "s"} earned</p>
            <Link href="/contests/certificates" className="mt-3 inline-block text-sm text-brand-600 dark:text-brand-400 hover:underline">
              View certificates →
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
