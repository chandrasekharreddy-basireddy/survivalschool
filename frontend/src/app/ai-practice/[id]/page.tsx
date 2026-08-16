"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface OptionOut { id: string; text: string; order_index: number }
interface QuestionOut { id: string; prompt: string; options: OptionOut[] }
interface SessionOut { id: string; subject: string; question_count: number; provider: string; submitted_at: string | null; score_percent: number | null; questions: QuestionOut[] }
interface AnswerResult { question_id: string; prompt: string; is_correct: boolean; selected_option_ids: string[]; correct_option_ids: string[] }
interface ResultOut { id: string; subject: string; score_percent: number; answers: AnswerResult[] }
interface ExplanationOut { question_id: string; explanation: string; provider: string }

export default function AIPracticeSessionPage() {
  const params = useParams<{ id: string }>();
  const { user, loading } = useAuth();
  const toast = useToast();
  const [session, setSession] = useState<SessionOut | null>(null);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [result, setResult] = useState<ResultOut | null>(null);
  const [explanations, setExplanations] = useState<Record<string, ExplanationOut>>({});
  const [explaining, setExplaining] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<ResultOut>(`/ai-practice/sessions/${params.id}`)
      .then(setResult)
      .catch(async (err) => {
        if (err instanceof ApiError && err.status === 409) {
          try {
            const s = await apiFetch<SessionOut>(`/ai-practice/sessions/${params.id}/questions`);
            setSession(s);
          } catch {
            setError("Couldn't load this practice session.");
          }
        } else {
          setError(err instanceof ApiError ? err.message : "Couldn't load this practice session.");
        }
      });
  }, [user, params.id]);

  const toggleOption = (questionId: string, optionId: string) => {
    setAnswers((prev) => ({ ...prev, [questionId]: [optionId] }));
  };

  const submit = async () => {
    if (!session) return;
    setSubmitting(true);
    try {
      const res = await apiFetch<ResultOut>(`/ai-practice/sessions/${session.id}/submit`, {
        method: "POST",
        body: JSON.stringify({ answers: session.questions.map((q) => ({ question_id: q.id, selected_option_ids: answers[q.id] || [] })) }),
      });
      setResult(res);
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't submit.", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const explainWithAI = async (questionId: string) => {
    setExplaining((prev) => ({ ...prev, [questionId]: true }));
    try {
      const explanation = await apiFetch<ExplanationOut>(`/ai-practice/sessions/${params.id}/questions/${questionId}/explanation`, {
        method: "POST",
      });
      setExplanations((prev) => ({ ...prev, [questionId]: explanation }));
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't generate an AI explanation.", "error");
    } finally {
      setExplaining((prev) => ({ ...prev, [questionId]: false }));
    }
  };

  if (loading) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) return <div className="mx-auto max-w-md px-6 py-24 text-center text-fg-muted">Sign in required.</div>;
  if (error) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-red-700 dark:text-red-400">{error}</p>
        <Link href="/ai-practice" className="btn-secondary mt-6 inline-flex">Back to AI practice</Link>
      </div>
    );
  }

  if (result) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-5 lg:px-6">
        <div className="card text-center">
          <p className="text-sm uppercase tracking-widest text-fg-subtle">AI practice — {result.subject}</p>
          <p className="mt-2 text-4xl font-bold text-fg">{result.score_percent}%</p>
          <p className="mt-2 text-sm text-fg-muted">AI-generated, for practice only — no points, no grade, no certificate impact.</p>
          <Link href="/ai-practice" className="btn-secondary mt-5 inline-flex">Back to AI practice</Link>
        </div>
        <div className="mt-6 space-y-4">
          {result.answers.map((a, idx) => (
            <div key={a.question_id} className={`card ${a.is_correct ? "border-emerald-500/40" : "border-red-500/40"}`}>
              <p className="font-medium text-fg">{idx + 1}. {a.prompt}</p>
              <p className={`mt-2 text-sm font-medium ${a.is_correct ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}`}>
                {a.is_correct ? "Correct" : "Incorrect"}
              </p>

              {explanations[a.question_id] ? (
                <div className="mt-4 rounded-lg border border-ink-700 bg-ink-950/40 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-fg">AI explanation</p>
                    <span className="text-xs text-fg-subtle">{explanations[a.question_id].provider}</span>
                  </div>
                  <div className="markdown-body mt-2 text-sm text-fg-muted">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{explanations[a.question_id].explanation}</ReactMarkdown>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => explainWithAI(a.question_id)}
                  disabled={Boolean(explaining[a.question_id])}
                  className="btn-secondary mt-4"
                >
                  {explaining[a.question_id] ? "Generating explanation…" : "Explain with AI"}
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!session) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Generating…</div>;

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-5 lg:px-6">
      <h1 className="text-2xl font-bold text-fg">AI practice — {session.subject}</h1>
      <p className="mt-1 text-sm text-fg-muted">
        {session.questions.length} AI-generated questions ({session.provider === "mock" ? "mock/dev provider" : "Sarvam AI"}) — for practice only, never graded toward anything real.
      </p>

      <div className="mt-6 space-y-5">
        {session.questions.map((q, idx) => (
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
                    <input type="radio" name={q.id} checked={selected} onChange={() => toggleOption(q.id, opt.id)} className="accent-brand-500" />
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
