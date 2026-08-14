"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

interface AttemptHistoryOut {
  id: string;
  quiz_id: string | null;
  exam_id: string | null;
  title: string;
  attempt_number: number;
  status: string;
  score_percent: number | null;
  passed: boolean | null;
  started_at: string;
  submitted_at: string | null;
}

export default function QuizHistoryPage() {
  const { user, loading } = useAuth();
  const [attempts, setAttempts] = useState<AttemptHistoryOut[] | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<AttemptHistoryOut[]>("/quizzes/me/attempts").then(setAttempts).catch(() => setAttempts([]));
  }, [user]);

  if (loading) return <div className="mx-auto max-w-4xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to see your quiz history.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Your quiz history</h1>
      <p className="mt-1 text-sm text-fg-muted">Every quiz attempt you&apos;ve made, most recent first.</p>

      {attempts === null ? (
        <p className="mt-8 text-sm text-fg-subtle">Loading…</p>
      ) : attempts.length === 0 ? (
        <div className="mt-8 rounded-lg border border-dashed border-ink-700 p-10 text-center text-sm text-fg-subtle">
          No quiz attempts yet — browse courses to find one.{" "}
          <Link href="/courses" className="text-brand-400 hover:underline">Browse courses</Link>
        </div>
      ) : (
        <div className="mt-8 space-y-3">
          {attempts.map((a) => {
            const inProgress = a.score_percent === null || a.status === "in_progress";
            return (
              <div key={a.id} className="card flex items-center justify-between gap-4">
                <div>
                  <p className="font-medium text-fg">{a.title}</p>
                  <p className="mt-1 text-xs text-fg-subtle">
                    Attempt #{a.attempt_number} &middot; Started {formatDateTime(a.started_at)}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  {inProgress ? (
                    <span className="rounded-full bg-ink-800 px-2.5 py-0.5 text-xs font-semibold text-fg-muted">
                      In progress
                    </span>
                  ) : (
                    <>
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                          a.passed ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-300"
                        }`}
                      >
                        {a.passed ? "Passed" : "Not passed"}
                      </span>
                      <p className="mt-1 text-sm text-fg">{a.score_percent}%</p>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
