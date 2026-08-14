"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatDuration } from "@/lib/format";

interface ExamMeta {
  id: string;
  title: string;
  time_limit_seconds: number;
  max_attempts: number;
  pass_score_percent: number;
  fullscreen_required: boolean;
  integrity_monitoring_enabled: boolean;
}

/** Event types the backend accepts on PUT /exams/attempts/{id}/events — see
 * IntegrityEventIn's regex pattern in app/schemas/assessment.py. Keep in sync. */
type IntegrityEventType = "tab_blur" | "fullscreen_exit" | "copy" | "paste" | "right_click";

interface OptionPublic { id: string; text: string; order_index: number }
interface QuestionPublic { id: string; prompt: string; question_type: string; points: number; options: OptionPublic[] }
interface StartResponse { attempt_id: string; server_deadline_at: string; remaining_seconds: number; resumed: boolean }
interface AttemptResult { id: string; status: string; score_percent: number | null; points_earned: number | null; points_possible: number | null; passed: boolean | null }

export default function ExamTakingPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { user, loading } = useAuth();
  const toast = useToast();

  const [meta, setMeta] = useState<ExamMeta | null>(null);
  const [starting, setStarting] = useState(false);
  const [attempt, setAttempt] = useState<StartResponse | null>(null);
  const [questions, setQuestions] = useState<QuestionPublic[] | null>(null);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [remaining, setRemaining] = useState<number>(0);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const submittedRef = useRef(false);
  const clientTokenRef = useRef<string>(crypto.randomUUID());

  useEffect(() => {
    apiFetch<ExamMeta>(`/exams/${params.id}`, { auth: false }).then(setMeta).catch(() => setMeta(null));
  }, [params.id]);

  const doSubmit = useCallback(async () => {
    if (!attempt || submittedRef.current) return;
    submittedRef.current = true;
    setSubmitting(true);
    try {
      const payload = {
        answers: (questions || []).map((q) => ({ question_id: q.id, selected_option_ids: answers[q.id] || [] })),
        client_token: clientTokenRef.current,
      };
      const res = await apiFetch<AttemptResult>(`/exams/attempts/${attempt.attempt_id}/submit`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setResult(res);
      toast.show("Exam submitted.", res.passed ? "success" : "info");
    } catch (err) {
      submittedRef.current = false;
      setError(err instanceof ApiError ? err.message : "Couldn't submit the exam — check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt, questions, answers]);

  useEffect(() => {
    if (!attempt || result) return;
    const deadline = new Date(attempt.server_deadline_at).getTime();
    const tick = () => {
      const secs = Math.max(0, Math.round((deadline - Date.now()) / 1000));
      setRemaining(secs);
      if (secs <= 0) doSubmit();
    };
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [attempt, result, doSubmit]);

  useEffect(() => {
    if (result && typeof document !== "undefined" && document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    }
  }, [result]);

  const reportIntegrityEvent = useCallback((eventType: IntegrityEventType) => {
    if (!attempt) return;
    apiFetch(`/exams/attempts/${attempt.attempt_id}/events`, {
      method: "PUT",
      body: JSON.stringify({ event_type: eventType }),
    }).catch(() => {
      // Best-effort and non-blocking by design — see report_integrity_event
      // in app/api/v1/exams.py. A network hiccup here must never surface to
      // the student or interrupt their attempt.
    });
  }, [attempt]);

  useEffect(() => {
    if (!attempt || result || !meta?.integrity_monitoring_enabled) return;

    const onVisibility = () => { if (document.hidden) reportIntegrityEvent("tab_blur"); };
    const onFullscreenChange = () => {
      if (meta.fullscreen_required && !document.fullscreenElement) reportIntegrityEvent("fullscreen_exit");
    };
    const onCopy = () => reportIntegrityEvent("copy");
    const onPaste = () => reportIntegrityEvent("paste");
    const onContextMenu = () => reportIntegrityEvent("right_click");

    document.addEventListener("visibilitychange", onVisibility);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    document.addEventListener("copy", onCopy);
    document.addEventListener("paste", onPaste);
    document.addEventListener("contextmenu", onContextMenu);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      document.removeEventListener("fullscreenchange", onFullscreenChange);
      document.removeEventListener("copy", onCopy);
      document.removeEventListener("paste", onPaste);
      document.removeEventListener("contextmenu", onContextMenu);
    };
  }, [attempt, result, meta, reportIntegrityEvent]);

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      const startRes = await apiFetch<StartResponse>(`/exams/${params.id}/attempts`, { method: "POST" });
      const qs = await apiFetch<QuestionPublic[]>(`/exams/attempts/${startRes.attempt_id}/questions`);
      setAttempt(startRes);
      setQuestions(qs);
      if (meta?.fullscreen_required && document.documentElement.requestFullscreen) {
        document.documentElement.requestFullscreen().catch(() => {
          // Fullscreen can be blocked by the browser/OS. The attempt still
          // proceeds either way — declining fullscreen is itself caught by
          // the fullscreenchange listener above and logged for instructor
          // review, never used to auto-fail the student.
        });
      }
      if (startRes.resumed) {
        toast.show("Resumed your in-progress attempt. Previously saved answers still count even if selections aren't shown below.", "info");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't start the exam.");
    } finally {
      setStarting(false);
    }
  };

  const toggleOption = async (question: QuestionPublic, optionId: string) => {
    if (!attempt) return;
    const single = question.question_type === "single" || question.question_type === "true_false";
    const current = answers[question.id] || [];
    const next = single ? [optionId] : current.includes(optionId) ? current.filter((o) => o !== optionId) : [...current, optionId];
    setAnswers((prev) => ({ ...prev, [question.id]: next }));
    try {
      await apiFetch(`/exams/attempts/${attempt.attempt_id}/autosave`, {
        method: "PUT",
        body: JSON.stringify({ question_id: question.id, selected_option_ids: next }),
      });
    } catch {
      // Autosave failures are non-fatal here — the final submit payload still
      // carries the answer from local state; a persistent autosave outage
      // would only matter if the tab crashes before submit, which the toast
      // below at least surfaces so the student knows to be careful.
      toast.show("Autosave failed — your answer is still recorded locally, but stay connected until you submit.", "error");
    }
  };

  if (loading) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to take this exam.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  if (result) {
    return (
      <div className="mx-auto max-w-lg px-6 py-16 text-center">
        <div className={`card ${result.passed ? "border-emerald-500/40" : "border-amber-500/40"}`}>
          <p className="text-sm uppercase tracking-widest text-fg-subtle">Exam complete</p>
          <p className="mt-2 text-4xl font-bold text-fg">{result.score_percent ?? 0}%</p>
          <p className="mt-2 text-sm text-fg-muted">
            {result.points_earned} / {result.points_possible} points &middot; {result.passed ? "Passed" : "Not passed"}
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Link href="/dashboard" className="btn-secondary">Dashboard</Link>
            <button onClick={() => router.push(`/exams/${params.id}/review`)} className="btn-primary">Review answers</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-fg">{meta?.title || "Exam"}</h1>
          {meta && <p className="mt-1 text-sm text-fg-muted">Pass at {meta.pass_score_percent}% &middot; {Math.round(meta.time_limit_seconds / 60)} min</p>}
        </div>
        {attempt && !result && (
          <div className={`rounded-lg border px-4 py-2 text-center font-mono text-lg ${remaining < 60 ? "border-red-500/50 text-red-700 dark:text-red-400" : "border-ink-700 text-fg"}`}>
            {formatDuration(remaining)}
          </div>
        )}
      </div>

      {error && <p className="mt-4 text-sm text-red-700 dark:text-red-400">{error}</p>}

      {!attempt || !questions ? (
        <div className="card mt-8 text-center">
          <p className="text-sm text-fg-muted">
            This is a timed, proctored-lite exam. Once started, the clock runs until you submit or time expires — answers autosave as you go.
          </p>
          {meta?.integrity_monitoring_enabled && (
            <p className="mt-2 text-xs text-fg-subtle">
              {meta.fullscreen_required
                ? "This exam requires fullscreen. Switching tabs, leaving fullscreen, copying, or pasting is logged for your instructor to review — it won't auto-fail your attempt, but stay focused."
                : "Switching tabs, copying, or pasting during this exam is logged for your instructor to review — it won't auto-fail your attempt, but stay focused."}
            </p>
          )}
          <button onClick={start} disabled={starting} className="btn-primary mt-6">
            {starting ? "Starting…" : "Start exam"}
          </button>
        </div>
      ) : (
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

          <button onClick={doSubmit} disabled={submitting} className="btn-primary w-full">
            {submitting ? "Submitting…" : "Submit exam"}
          </button>
        </div>
      )}
    </div>
  );
}
