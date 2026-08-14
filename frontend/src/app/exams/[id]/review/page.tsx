"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";

interface ReviewAnswer {
  question_id: string;
  prompt: string;
  question_type: string;
  selected_option_ids: string[];
  correct_option_ids: string[];
  is_correct: boolean | null;
  points_awarded: number;
  points_possible: number;
  explanation: string | null;
}

interface AttemptReview {
  attempt_id: string;
  status: string;
  score_percent: number | null;
  passed: boolean | null;
  answers: ReviewAnswer[];
}

interface AttemptHistory {
  id: string;
  exam_id: string;
  title: string;
  status: string;
  score_percent: number | null;
  passed: boolean | null;
  submitted_at: string | null;
}

export default function ExamReviewPage() {
  const params = useParams<{ id: string }>();
  const { user, loading } = useAuth();
  const [review, setReview] = useState<AttemptReview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        // The review endpoint is keyed by attempt_id, not exam_id — find this
        // student's most recent submitted attempt for this exam first.
        const history = await apiFetch<AttemptHistory[]>("/exams/me/attempts");
        const latest = history.find((a) => a.exam_id === params.id && a.status === "submitted");
        if (!latest) {
          setError("No submitted attempt found for this exam yet.");
          return;
        }
        const rev = await apiFetch<AttemptReview>(`/exams/attempts/${latest.id}/review`);
        setReview(rev);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Couldn't load your exam review.");
      }
    })();
  }, [user, params.id]);

  if (loading) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to review your exam.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }
  if (error) {
    return (
      <div className="mx-auto max-w-lg px-6 py-24 text-center">
        <p className="text-fg-muted">{error}</p>
        <Link href="/dashboard" className="btn-secondary mt-6 inline-flex">Back to dashboard</Link>
      </div>
    );
  }
  if (!review) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Exam review</h1>
      <p className="mt-1 text-sm text-fg-muted">
        Score: {review.score_percent ?? 0}% &middot; {review.passed ? "Passed" : "Not passed"}
      </p>

      <div className="mt-8 space-y-4">
        {review.answers.map((a, idx) => (
          <div key={a.question_id} className={`card ${a.is_correct ? "border-emerald-500/30" : "border-red-500/30"}`}>
            <div className="flex items-start justify-between gap-3">
              <p className="font-medium text-fg">{idx + 1}. {a.prompt}</p>
              <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ${a.is_correct ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-red-300"}`}>
                {a.points_awarded}/{a.points_possible} pts
              </span>
            </div>
            {!a.is_correct && (
              <p className="mt-2 text-xs text-fg-subtle">
                Correct option{a.correct_option_ids.length > 1 ? "s" : ""} not selected.
              </p>
            )}
            {a.explanation && <p className="mt-2 text-sm text-fg-muted">{a.explanation}</p>}
          </div>
        ))}
      </div>

      <Link href="/dashboard" className="btn-secondary mt-8 inline-flex">Back to dashboard</Link>
    </div>
  );
}
