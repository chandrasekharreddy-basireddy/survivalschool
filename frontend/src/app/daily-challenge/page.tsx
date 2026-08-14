"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface OptionPublic { id: string; text: string; order_index: number }
interface QuestionPublic { id: string; prompt: string; question_type: string; points: number; options: OptionPublic[] }
interface AttemptOut { is_correct: boolean; points_awarded: number; selected_option_ids: string[]; correct_option_ids: string[] }
interface DailyChallenge {
  id: string;
  challenge_date: string;
  question: QuestionPublic;
  already_attempted: boolean;
  my_attempt: AttemptOut | null;
  current_streak_days: number;
}

export default function DailyChallengePage() {
  const { user, loading } = useAuth();
  const toast = useToast();
  const [challenge, setChallenge] = useState<DailyChallenge | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<DailyChallenge>("/daily-challenge/today")
      .then(setChallenge)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't load today's challenge."));
  }, [user]);

  const submit = async () => {
    if (!selected || !challenge) return;
    setSubmitting(true);
    try {
      const res = await apiFetch<DailyChallenge>("/daily-challenge/today/attempt", {
        method: "POST",
        body: JSON.stringify({ selected_option_ids: [selected] }),
      });
      setChallenge(res);
      toast.show(
        res.my_attempt?.is_correct ? `Correct! +${res.my_attempt.points_awarded} points.` : "Not quite — see the answer below.",
        res.my_attempt?.is_correct ? "success" : "error"
      );
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't submit your answer.", "error");
      if (err instanceof ApiError && err.status === 422) {
        // Most likely lost a race with another request answering today's
        // challenge first (e.g. a double-click, or another tab) — refetch
        // so the UI reflects the real server state instead of staying
        // stuck showing an answerable question that's actually already done.
        apiFetch<DailyChallenge>("/daily-challenge/today").then(setChallenge).catch(() => {});
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="mx-auto max-w-2xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to take today&apos;s challenge.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-fg">Daily challenge</h1>
        {challenge && (
          <span className="flex items-center gap-1 rounded-full bg-brand-500/10 px-3 py-1 text-sm font-medium text-brand-600 dark:text-brand-400">
            🔥 {challenge.current_streak_days} day streak
          </span>
        )}
      </div>
      <p className="mt-2 text-sm text-fg-muted">
        One real question, the same for every student, every day. Answer correctly for bonus points and to keep your streak alive.
      </p>

      {error ? (
        <div className="card mt-8 text-center">
          <p className="text-sm text-fg-subtle">{error}</p>
        </div>
      ) : challenge === null ? (
        <div className="card mt-8 text-center text-sm text-fg-subtle">Loading today&apos;s challenge…</div>
      ) : (
        <div className="card mt-8">
          <p className="text-xs font-medium uppercase tracking-wide text-fg-subtle">
            Today · {new Date(challenge.challenge_date).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
          </p>
          <p className="mt-3 text-lg font-medium text-fg">{challenge.question.prompt}</p>

          <div className="mt-5 space-y-2">
            {challenge.question.options.map((opt) => {
              const attempted = challenge.already_attempted;
              const isMine = challenge.my_attempt?.selected_option_ids.includes(opt.id);
              const isCorrectOption = challenge.my_attempt?.correct_option_ids.includes(opt.id);
              const showResult = attempted && challenge.my_attempt;

              let stateClasses = "border-ink-700 hover:border-brand-500/50";
              if (showResult && isCorrectOption) stateClasses = "border-emerald-500 bg-emerald-500/10";
              else if (showResult && isMine && !isCorrectOption) stateClasses = "border-red-500 bg-red-500/10";
              else if (!attempted && selected === opt.id) stateClasses = "border-brand-500 bg-brand-500/10";

              return (
                <button
                  key={opt.id}
                  onClick={() => !attempted && setSelected(opt.id)}
                  disabled={attempted}
                  className={`w-full rounded-lg border px-4 py-3 text-left text-sm text-fg transition ${stateClasses} ${attempted ? "cursor-default" : "cursor-pointer"}`}
                >
                  {opt.text}
                  {showResult && isCorrectOption && <span className="ml-2 text-xs text-emerald-700 dark:text-emerald-400">✓ correct answer</span>}
                  {showResult && isMine && !isCorrectOption && <span className="ml-2 text-xs text-red-700 dark:text-red-400">your answer</span>}
                </button>
              );
            })}
          </div>

          {!challenge.already_attempted ? (
            <button onClick={submit} disabled={!selected || submitting} className="btn-primary mt-6 w-full">
              {submitting ? "Submitting…" : "Submit answer"}
            </button>
          ) : (
            <div className="mt-6 rounded-lg border border-ink-700 p-4 text-center">
              <p className="text-sm font-medium text-fg">
                {challenge.my_attempt?.is_correct
                  ? `Nice — you earned ${challenge.my_attempt.points_awarded} points today.`
                  : "You've already answered today's challenge."}
              </p>
              <p className="mt-1 text-xs text-fg-subtle">Come back tomorrow for a new one.</p>
              <Link href="/daily-challenge/history" className="mt-3 inline-block text-sm text-brand-600 hover:underline dark:text-brand-400">
                View your history →
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
