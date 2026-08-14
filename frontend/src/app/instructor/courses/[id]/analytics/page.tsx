"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError, getAccessToken } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

interface Overview {
  enrolled_count: number;
  completed_count: number;
  completion_rate_percent: number;
  quiz_attempts_count: number;
  exam_attempts_count: number;
  average_quiz_score_percent: number | null;
  average_exam_score_percent: number | null;
  score_distribution: Record<string, number>;
}

interface QuestionStat {
  question_id: string;
  prompt: string;
  question_type: string;
  times_answered: number;
  times_correct: number;
  percent_correct: number;
}

const BUCKET_ORDER = ["0-59", "60-69", "70-79", "80-89", "90-100"];

export default function CourseAnalyticsPage() {
  const params = useParams<{ id: string }>();
  const { user, loading } = useAuth();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [questions, setQuestions] = useState<QuestionStat[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    Promise.all([
      apiFetch<Overview>(`/courses/${params.id}/analytics/overview`),
      apiFetch<QuestionStat[]>(`/courses/${params.id}/analytics/questions`),
    ])
      .then(([o, q]) => {
        setOverview(o);
        setQuestions(q);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't load analytics."));
  }, [user, params.id]);

  const downloadCsv = async () => {
    const token = getAccessToken();
    const resp = await fetch(`${API_BASE}/courses/${params.id}/analytics/export.csv`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "question-analytics.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) return <div className="mx-auto max-w-4xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) return <div className="mx-auto max-w-md px-6 py-24 text-center text-fg-muted">Sign in required.</div>;
  if (error) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-red-400">{error}</p>
        <Link href="/instructor/courses" className="btn-secondary mt-6 inline-flex">Back to your courses</Link>
      </div>
    );
  }

  const maxBucket = overview ? Math.max(1, ...BUCKET_ORDER.map((b) => overview.score_distribution[b] || 0)) : 1;

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-fg">Course analytics</h1>
        <button onClick={downloadCsv} className="btn-secondary">Export question data (.csv)</button>
      </div>

      {overview && (
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Enrolled" value={overview.enrolled_count} />
          <StatCard label="Completed" value={`${overview.completion_rate_percent}%`} sub={`${overview.completed_count} of ${overview.enrolled_count}`} />
          <StatCard label="Avg quiz score" value={overview.average_quiz_score_percent != null ? `${overview.average_quiz_score_percent}%` : "—"} sub={`${overview.quiz_attempts_count} attempts`} />
          <StatCard label="Avg exam score" value={overview.average_exam_score_percent != null ? `${overview.average_exam_score_percent}%` : "—"} sub={`${overview.exam_attempts_count} attempts`} />
        </div>
      )}

      {overview && (
        <div className="card mt-6">
          <h2 className="font-semibold text-fg">Score distribution</h2>
          <div className="mt-4 space-y-2">
            {BUCKET_ORDER.map((bucket) => {
              const count = overview.score_distribution[bucket] || 0;
              return (
                <div key={bucket} className="flex items-center gap-3">
                  <span className="w-14 shrink-0 text-xs text-fg-subtle">{bucket}%</span>
                  <div className="h-3 flex-1 overflow-hidden rounded-full bg-ink-800">
                    <div className="h-full rounded-full bg-brand-500" style={{ width: `${(count / maxBucket) * 100}%` }} />
                  </div>
                  <span className="w-6 shrink-0 text-right text-xs text-fg-subtle">{count}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="card mt-6">
        <h2 className="font-semibold text-fg">Per-question difficulty</h2>
        <p className="mt-1 text-xs text-fg-subtle">Lowest percent-correct first — these are the questions students struggle with most.</p>
        {questions === null ? (
          <p className="mt-4 text-sm text-fg-subtle">Loading…</p>
        ) : questions.length === 0 ? (
          <p className="mt-4 text-sm text-fg-subtle">No answered questions yet.</p>
        ) : (
          <div className="mt-4 space-y-2">
            {questions.map((q) => (
              <div key={q.question_id} className="flex items-center justify-between gap-4 border-b border-ink-800 py-2.5 last:border-0">
                <div className="min-w-0">
                  <p className="truncate text-sm text-fg">{q.prompt}</p>
                  <p className="text-xs text-fg-subtle">{q.times_answered} answered · {q.times_correct} correct</p>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                    q.percent_correct < 50 ? "bg-red-500/15 text-red-300" : q.percent_correct < 80 ? "bg-amber-500/15 text-amber-300" : "bg-emerald-500/15 text-emerald-300"
                  }`}
                >
                  {q.percent_correct}%
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="card !p-4">
      <p className="text-xs uppercase tracking-wide text-fg-subtle">{label}</p>
      <p className="mt-1 text-2xl font-bold text-fg">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-fg-subtle">{sub}</p>}
    </div>
  );
}
