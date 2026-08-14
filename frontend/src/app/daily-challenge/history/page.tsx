"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";

interface HistoryEntry { challenge_date: string; is_correct: boolean; points_awarded: number; answered_at: string }

export default function DailyChallengeHistoryPage() {
  const { user, loading } = useAuth();
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<HistoryEntry[]>("/daily-challenge/history")
      .then(setEntries)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't load your history."));
  }, [user]);

  if (loading) return <div className="mx-auto max-w-2xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to view your daily challenge history.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-fg">Your daily challenge history</h1>
        <Link href="/daily-challenge" className="text-sm text-brand-600 hover:underline dark:text-brand-400">Today&apos;s challenge →</Link>
      </div>

      <div className="card mt-6">
        {error ? (
          <p className="text-sm text-fg-subtle">{error}</p>
        ) : entries === null ? (
          <p className="text-sm text-fg-subtle">Loading…</p>
        ) : entries.length === 0 ? (
          <p className="text-sm text-fg-subtle">You haven&apos;t answered a daily challenge yet.</p>
        ) : (
          <ul className="divide-y divide-ink-800">
            {entries.map((e) => (
              <li key={e.challenge_date} className="flex items-center justify-between py-3">
                <span className="text-sm text-fg">
                  {new Date(e.challenge_date).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
                </span>
                <span className={`text-sm font-medium ${e.is_correct ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}`}>
                  {e.is_correct ? `Correct · +${e.points_awarded}` : "Missed"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
