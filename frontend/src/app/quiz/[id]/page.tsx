"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface QuizMeta {
  id: string;
  title: string;
  time_limit_seconds: number | null;
  max_attempts: number;
  pass_score_percent: number;
  is_published: boolean;
}

interface OptionPublic {
  id: string;
  text: string;
  order_index: number;
}

interface QuestionPublic {
  id: string;
  prompt: string;
  question_type: string;
  points: number;
  options: OptionPublic[];
}

interface AttemptResult {
  id: string;
  status: string;
  score_percent: number | null;
  points_earned: number | null;
  points_possible: number | null;
  passed: boolean | null;
}

export default function QuizTakingPage() {
  const params = useParams<{ id: string }>();
  const { user, loading } = useAuth();
  const toast = useToast();

  const [meta, setMeta] = useState<QuizMeta | null>(null);
  const [questions, setQuestions] = useState<QuestionPublic[] | null>(null);
  const [attemptId, setAttemptId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [starting, setStarting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<QuizMeta>(`/quizzes/${params.id}`, { auth: false }).then(setMeta).catch(() => setMeta(null));
  }, [params.id]);

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      const qs = await apiFetch<QuestionPublic[]>(`/quizzes/${params.id}/attempts`, { method: "POST" });
      const current = await apiFetch<{ attempt_id: string }>(`/quizzes/${params.id}/attempts/current`);
      setQuestions(qs);
      setAttemptId(current.attempt_id);
      setAnswers({});
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't start the quiz. Please try again.");
    } finally {
      setStarting(false);
    }
  };

  const toggleOption = (question: QuestionPublic, optionId: string) => {
    setAnswers((prev) => {
      const current = prev[question.id] || [];
      if (question.question_type === "single" || question.question_type === "true_false") {
        return { ...prev, [question.id]: [optionId] };
      }
      const next = current.includes(optionId) ? current.filter((o) => o !== optionId) : [...current, optionId];
      return { ...prev, [question.id]: next };
    });
  };

  const submit = async () => {
    if (!attemptId || !questions) return;
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        answers: questions.map((q) => ({
          question_id: q.id,
          selected_option_ids: answers[q.id] || [],
        })),
      };
      const res = await apiFetch<AttemptResult>(`/quizzes/attempts/${attemptId}/submit`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setResult(res);
      toast.show(res.passed ? "Nice work — you passed!" : "Quiz submitted.", res.passed ? "success" : "info");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't submit the quiz.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to take this quiz.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  if (result) {
    return (
      <div className="mx-auto max-w-lg px-6 py-16 text-center">
        <div className={`card ${result.passed ? "border-emerald-500/40" : "border-amber-500/40"}`}>
          <p className="text-sm uppercase tracking-widest text-fg-subtle">Quiz complete</p>
          <p className="mt-2 text-4xl font-bold text-fg">{result.score_percent ?? 0}%</p>
          <p className="mt-2 text-sm text-fg-muted">
            {result.points_earned} / {result.points_possible} points &middot; {result.passed ? "Passed" : "Not passed"}
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Link href="/dashboard" className="btn-secondary">Back to dashboard</Link>
            {meta && !result.passed && questions && questions.length > 0 && (
              <button onClick={() => { setResult(null); setQuestions(null); setAttemptId(null); }} className="btn-primary">
                Try again
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">{meta?.title || "Quiz"}</h1>
      {meta && (
        <p className="mt-1 text-sm text-fg-muted">
          {meta.max_attempts} attempt{meta.max_attempts === 1 ? "" : "s"} allowed &middot; pass at {meta.pass_score_percent}%
          {meta.time_limit_seconds ? ` · ${Math.round(meta.time_limit_seconds / 60)} min limit` : ""}
        </p>
      )}

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      {!questions ? (
        <div className="card mt-8 text-center">
          <p className="text-sm text-fg-muted">
            Starting uses one of your quiz attempts. Answer every question before submitting — you can&apos;t restart mid-quiz.
          </p>
          <button onClick={start} disabled={starting} className="btn-primary mt-6">
            {starting ? "Starting…" : "Start quiz"}
          </button>
        </div>
      ) : (
        <div className="mt-8 space-y-6">
          {questions.map((q, idx) => (
            <div key={q.id} className="card">
              <div className="flex items-start justify-between gap-3">
                <p className="font-medium text-fg">{idx + 1}. {q.prompt}</p>
                <BookmarkButton questionId={q.id} />
              </div>
              <div className="mt-4 space-y-2">
                {q.options.map((opt) => {
                  const selected = (answers[q.id] || []).includes(opt.id);
                  return (
                    <label
                      key={opt.id}
                      className={`flex cursor-pointer items-center gap-3 rounded-lg border px-4 py-2.5 text-sm transition ${
                        selected ? "border-brand-500 bg-brand-500/10 text-brand-700 dark:text-white" : "border-ink-700 text-fg-muted hover:border-ink-600"
                      }`}
                    >
                      <input
                        type={q.question_type === "multiple" ? "checkbox" : "radio"}
                        name={q.id}
                        checked={selected}
                        onChange={() => toggleOption(q, opt.id)}
                        className="accent-brand-500"
                      />
                      {opt.text}
                    </label>
                  );
                })}
              </div>
            </div>
          ))}

          <button onClick={submit} disabled={submitting} className="btn-primary w-full">
            {submitting ? "Submitting…" : "Submit quiz"}
          </button>
        </div>
      )}
    </div>
  );
}

/** Bookmark a question for later review in Practice mode (see /practice) —
 * independent of whether it's answered correctly here; students often want
 * to revisit a question that was hard, not just ones they got wrong. */
function BookmarkButton({ questionId }: { questionId: string }) {
  const [bookmarked, setBookmarked] = useState(false);
  const [busy, setBusy] = useState(false);

  const toggle = async () => {
    setBusy(true);
    try {
      if (bookmarked) {
        await apiFetch(`/questions/${questionId}/bookmark`, { method: "DELETE" });
        setBookmarked(false);
      } else {
        await apiFetch(`/questions/${questionId}/bookmark`, { method: "POST", body: JSON.stringify({}) });
        setBookmarked(true);
      }
    } catch {
      /* non-critical UI affordance — silently no-op on failure */
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      onClick={toggle}
      disabled={busy}
      aria-label={bookmarked ? "Remove bookmark" : "Bookmark this question"}
      title={bookmarked ? "Remove bookmark" : "Bookmark for practice later"}
      className={`shrink-0 rounded-lg p-1.5 transition ${bookmarked ? "text-amber-400" : "text-fg-subtle hover:text-fg"}`}
    >
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill={bookmarked ? "currentColor" : "none"} stroke="currentColor" strokeWidth={1.75} className="h-5 w-5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 3.75A2.25 2.25 0 0 1 8.25 1.5h7.5A2.25 2.25 0 0 1 18 3.75v16.5a.75.75 0 0 1-1.164.624L12 17.25l-4.836 3.624A.75.75 0 0 1 6 20.25V3.75Z" />
      </svg>
    </button>
  );
}
