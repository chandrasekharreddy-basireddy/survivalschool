"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";
import { PageLoader } from "@/components/PageLoader";

interface PointsEntry {
  rank: number;
  student_id: string;
  full_name: string;
  total_points: number;
}

interface WinsEntry {
  rank: number;
  student_id: string;
  public_handle: string | null;
  full_name: string;
  wins: number;
}

const MEDALS = ["🥇", "🥈", "🥉"];
const TABS = [
  { key: "points", label: "Points" },
  { key: "ai-weekly", label: "AI Weekly Exam wins" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

function displayName(handle: string | null | undefined, fullName: string): string {
  return handle ? `@${handle}` : fullName;
}

export default function LeaderboardPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<TabKey>("points");
  const [pointsEntries, setPointsEntries] = useState<PointsEntry[] | null>(null);
  const [winsEntries, setWinsEntries] = useState<WinsEntry[] | null>(null);
  const [pointsError, setPointsError] = useState(false);
  const [winsError, setWinsError] = useState(false);

  useEffect(() => {
    apiFetch<PointsEntry[]>("/gamification/leaderboard?limit=50", { auth: false })
      .then(setPointsEntries)
      .catch(() => setPointsError(true));
    apiFetch<WinsEntry[]>("/contests/ai-weekly/leaderboard?limit=50", { auth: false })
      .then(setWinsEntries)
      .catch(() => setWinsError(true));
  }, []);

  const error = tab === "points" ? pointsError : winsError;

  const entries: { rank: number; student_id: string; name: string; stat: string }[] | null =
    tab === "points"
      ? pointsEntries?.map((e) => ({ rank: e.rank, student_id: e.student_id, name: e.full_name, stat: `${e.total_points} pts` })) ?? null
      : winsEntries?.map((e) => ({ rank: e.rank, student_id: e.student_id, name: displayName(e.public_handle, e.full_name), stat: `${e.wins} win${e.wins === 1 ? "" : "s"}` })) ?? null;

  const top3 = (entries || []).slice(0, 3);
  const rest = (entries || []).slice(3);

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Leaderboard</h1>
      <p className="mt-1 text-sm text-fg-muted">
        {tab === "points"
          ? "Top students by total points earned across contests, elimination battles, and the daily challenge."
          : "Who has won the most AI Weekly Exams — rank-1 finishes only."}
      </p>

      <div className="mt-6 inline-flex rounded-lg border border-ink-700 p-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              tab === t.key ? "bg-ink-800 text-fg" : "text-fg-muted hover:text-fg"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <p className="mt-8 text-sm text-red-700 dark:text-red-400">Couldn&apos;t load the leaderboard right now.</p>}

      {entries === null && !error ? (
        <p className="mt-8 text-sm text-fg-subtle"><PageLoader size="sm" /></p>
      ) : entries && entries.length === 0 ? (
        <div className="mt-8 rounded-lg border border-dashed border-ink-700 p-10 text-center text-sm text-fg-subtle">
          {tab === "points" ? "No points earned yet — be the first on the board." : "No AI Weekly Exam wins yet — be the first."}
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
                    <p className={`mt-2 truncate font-semibold ${entry.student_id === user?.id ? "text-brand-600 dark:text-brand-400" : "text-fg"}`}>{entry.name}</p>
                    <p className="text-xs text-fg-subtle">{entry.stat}</p>
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
                    <span className="text-sm font-medium">{e.name}</span>
                  </div>
                  <span className="text-sm text-fg-muted">{e.stat}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
