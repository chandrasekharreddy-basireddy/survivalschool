"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface OptionPublic { id: string; text: string; order_index: number }
interface QuestionPublic { id: string; prompt: string; question_type: string; points: number; options: OptionPublic[] }
interface AnswerResult { question_id: string; prompt: string; is_correct: boolean; selected_option_ids: string[]; correct_option_ids: string[]; explanation: string | null }
interface Result { id: string; source: string; score_percent: number; points_earned: number; points_possible: number; answers: AnswerResult[] }

export default function PracticeSessionPage() {
  const params = useParams<{ id: string }>();
  const { user, loading } = useAuth();
  const toast = useToast();
  const [questions, setQuestions] = useState<QuestionPublic[] | null>(null);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    // Already-submitted sessions resolve straight to their result (a page
    // refresh after submitting shows the same review, not a blank form).
    apiFetch<Result>(`/practice/sessions/${params.id}`)
      .then(setResult)
      .catch(async (err) => {
        if (err instanceof ApiError && err.status === 409) {
          try {
            const qs = await apiFetch<QuestionPublic[]>(`/practice/sessions/${params.id}/questions`);
            setQuestions(qs);
          } catch {
            setError("Couldn't load this practice session.");
          }
        } else {
          setError(err instanceof ApiError ? err.message : "Couldn't load this practice session.");
        }
      });
  }, [user, params.id]);

  const toggleOption = (question: QuestionPublic, optionId: string) => {
    setAnswers((prev) => {
      const single = question.question_type === "single" || question.question_type === "true_false";
      if (single) return { ...prev, [question.id]: [optionId] };
      const current = prev[question.id] || [];
      const next = current.includes(optionId) ? current.filter((o) => o !== optionId) : [...current, optionId];
      return { ...prev, [question.id]: next };
    });
  };

  const submit = async () => {
    if (!questions) return;
    setSubmitting(true);
    try {
      const res = await apiFetch<Result>(`/practice/sessions/${params.id}/submit`, {
        method: "POST",
        body: JSON.stringify({
          answers: questions.map((q) => ({ question_id: q.id, selected_option_ids: answers[q.id] || [] })),
        }),
      });
      setResult(res);
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't submit.", "error");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) return <div className="mx-auto max-w-md px-6 py-24 text-center text-fg-muted">Sign in required.</div>;
  if (error) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-red-700 dark:text-red-400">{error}</p>
        <Link href="/practice" className="btn-secondary mt-6 inline-flex">Back to practice</Link>
      </div>
    );
  }

  if (result) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-10">
        <div className="card text-center">
          <p className="text-sm uppercase tracking-widest text-fg-subtle">Practice complete</p>
          <p className="mt-2 text-4xl font-bold text-fg">{result.score_percent}%</p>
          <p className="mt-2 text-sm text-fg-muted">{result.points_earned} / {result.points_possible} points · no points or certificate progress from practice mode</p>
          <Link href="/practice" className="btn-secondary mt-6 inline-flex">Back to practice</Link>
        </div>

        <div className="mt-8 space-y-4">
          {result.answers.map((a, idx) => (
            <div key={a.question_id} className={`card ${a.is_correct ? "border-emerald-500/40" : "border-red-500/40"}`}>
              <p className="font-medium text-fg">{idx + 1}. {a.prompt}</p>
              <p className={`mt-2 text-sm font-medium ${a.is_correct ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}`}>
                {a.is_correct ? "Correct" : "Incorrect"}
              </p>
              {a.explanation && <p className="mt-2 text-sm text-fg-muted">{a.explanation}</p>}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!questions) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Practice session</h1>
      <p className="mt-1 text-sm text-fg-muted">Untimed — take your time. You&apos;ll see the correct answer for every question once you submit.</p>

      <div className="mt-8 space-y-6">
        {questions.map((q, idx) => (
          <div key={q.id} className="card">
            <p className="font-medium text-fg">{idx + 1}. {q.prompt}</p>
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
          {submitting ? "Submitting…" : "Submit and see answers"}
        </button>
      </div>
    </div>
  );
}
