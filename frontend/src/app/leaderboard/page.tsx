"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";

interface LeaderboardEntry {
  rank: number;
  student_id: string;
  full_name: string;
  total_points: number;
}

const MEDALS = ["🥇", "🥈", "🥉"];

export default function LeaderboardPage() {
  const { user } = useAuth();
  const [entries, setEntries] = useState<LeaderboardEntry[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    apiFetch<LeaderboardEntry[]>("/gamification/leaderboard?limit=50", { auth: false })
      .then(setEntries)
      .catch(() => setError(true));
  }, []);

  const top3 = (entries || []).slice(0, 3);
  const rest = (entries || []).slice(3);

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Leaderboard</h1>
      <p className="mt-1 text-sm text-fg-muted">Top learners by total points earned across courses, quizzes, and exams.</p>

      {error && <p className="mt-8 text-sm text-red-700 dark:text-red-400">Couldn&apos;t load the leaderboard right now.</p>}

      {entries === null && !error ? (
        <p className="mt-8 text-sm text-fg-subtle">Loading…</p>
      ) : entries && entries.length === 0 ? (
        <div className="mt-8 rounded-lg border border-dashed border-ink-700 p-10 text-center text-sm text-fg-subtle">
          No points earned yet — be the first on the board.
        </div>
      ) : (
        <>
          {top3.length > 0 && (
            <div className="mt-10 grid grid-cols-3 items-end gap-4">
              {[top3[1], top3[0], top3[2]].map((entry, i) =>
                entry ? (
                  <div
                    key={entry.student_id}
                    className={`card text-center ${entry.rank === 1 ? "order-2 border-amber-400/50 bg-amber-400/5" : i === 0 ? "order-1" : "order-3"}`}
                    style={{ paddingTop: entry.rank === 1 ? "2rem" : "1rem" }}
                  >
                    <div className="text-3xl">{MEDALS[entry.rank - 1]}</div>
                    <p className={`mt-2 truncate font-semibold ${entry.student_id === user?.id ? "text-brand-600 dark:text-brand-400" : "text-fg"}`}>{entry.full_name}</p>
                    <p className="text-xs text-fg-subtle">{entry.total_points} pts</p>
                  </div>
                ) : (
                  <div key={i} />
                )
              )}
            </div>
          )}

          {rest.length > 0 && (
            <ul className="card mt-6 divide-y divide-ink-800">
              {rest.map((e) => (
                <li key={e.student_id} className={`flex items-center justify-between py-3 ${e.student_id === user?.id ? "text-brand-600 dark:text-brand-400" : "text-fg"}`}>
                  <div className="flex items-center gap-4">
                    <span className="w-6 text-right text-sm text-fg-subtle">{e.rank}</span>
                    <span className="text-sm font-medium">{e.full_name}</span>
                  </div>
                  <span className="text-sm text-fg-muted">{e.total_points} pts</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
