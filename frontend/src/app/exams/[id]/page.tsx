"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatDuration } from "@/lib/format";
import { ExamIntegrityGuard } from "@/components/exams/ExamIntegrityGuard";

interface ExamMeta {
  id: string;
  title: string;
  time_limit_seconds: number;
  max_attempts: number;
  pass_score_percent: number;
  fullscreen_required: boolean;
  integrity_monitoring_enabled: boolean;
}

type IntegrityEventType = "tab_blur" | "fullscreen_exit" | "copy" | "paste" | "right_click";
interface OptionPublic { id: string; text: string; order_index: number }
interface QuestionPublic { id: string; prompt: string; question_type: string; points: number; options: OptionPublic[] }
interface StartResponse { attempt_id: string; server_deadline_at: string; remaining_seconds: number; resumed: boolean }
interface AttemptResult { id: string; status: string; score_percent: number | null; points_earned: number | null; points_possible: number | null; passed: boolean | null }

function TimerRing({ remaining, total }: { remaining: number; total: number }) {
  const safeTotal = Math.max(1, total);
  const progress = Math.max(0, Math.min(1, remaining / safeTotal));
  const radius = 29;
  const circumference = 2 * Math.PI * radius;
  const dash = circumference * progress;
  const urgent = remaining <= 60;
  const warning = remaining <= Math.max(180, Math.round(total * 0.2));
  const label = urgent ? "text-red-500" : warning ? "text-amber-500" : "text-fg";
  return (
    <div className="relative h-20 w-20 shrink-0" aria-label={`Time remaining ${formatDuration(remaining)}`}>
      <svg viewBox="0 0 72 72" className="h-full w-full -rotate-90">
        <circle cx="36" cy="36" r={radius} fill="none" stroke="currentColor" strokeWidth="5" className="text-ink-700/60" />
        <circle cx="36" cy="36" r={radius} fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeDasharray={`${dash} ${circumference - dash}`} className={urgent ? "text-red-500" : warning ? "text-amber-500" : "text-brand-500"} />
      </svg>
      <span className={`absolute inset-0 flex items-center justify-center font-mono text-[11px] font-bold ${label}`}>{formatDuration(remaining)}</span>
    </div>
  );
}

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
  const [flagged, setFlagged] = useState<Set<string>>(new Set());
  const [currentIndex, setCurrentIndex] = useState(0);
  const [remaining, setRemaining] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [showSummary, setShowSummary] = useState(false);
  const [fullscreenWarning, setFullscreenWarning] = useState(false);
  const submittedRef = useRef(false);
  const clientTokenRef = useRef<string>(crypto.randomUUID());
  const questionRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    apiFetch<ExamMeta>(`/exams/${params.id}`, { auth: false }).then(setMeta).catch(() => setMeta(null));
  }, [params.id]);

  const reportIntegrityEvent = useCallback((eventType: IntegrityEventType) => {
    if (!attempt) return;
    if (eventType === "fullscreen_exit") setFullscreenWarning(true);
    apiFetch(`/exams/attempts/${attempt.attempt_id}/events`, {
      method: "PUT",
      body: JSON.stringify({ event_type: eventType }),
    }).catch(() => {
      // Server-side integrity logging is best-effort and never interrupts an exam.
    });
  }, [attempt]);

  const doSubmit = useCallback(async () => {
    if (!attempt || submittedRef.current) return;
    submittedRef.current = true;
    setSubmitting(true);
    setShowSummary(false);
    try {
      const payload = {
        answers: (questions || []).map((q) => ({ question_id: q.id, selected_option_ids: answers[q.id] || [] })),
        client_token: clientTokenRef.current,
      };
      const res = await apiFetch<AttemptResult>(`/exams/attempts/${attempt.attempt_id}/submit`, { method: "POST", body: JSON.stringify(payload) });
      setResult(res);
      toast.show("Exam submitted.", res.passed ? "success" : "info");
    } catch (err) {
      submittedRef.current = false;
      setError(err instanceof ApiError ? err.message : "Couldn't submit the exam — check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  }, [attempt, questions, answers, toast]);

  useEffect(() => {
    if (!attempt || result) return;
    const deadline = new Date(attempt.server_deadline_at).getTime();
    const tick = () => {
      const secs = Math.max(0, Math.round((deadline - Date.now()) / 1000));
      setRemaining(secs);
      if (secs <= 0) void doSubmit();
    };
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [attempt, result, doSubmit]);

  useEffect(() => {
    if (result && typeof document !== "undefined" && document.fullscreenElement) document.exitFullscreen().catch(() => {});
  }, [result]);

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      const startRes = await apiFetch<StartResponse>(`/exams/${params.id}/attempts`, { method: "POST" });
      const qs = await apiFetch<QuestionPublic[]>(`/exams/attempts/${startRes.attempt_id}/questions`);
      setAttempt(startRes);
      setQuestions(qs);
      setCurrentIndex(0);
      if (meta?.fullscreen_required && document.documentElement.requestFullscreen) {
        document.documentElement.requestFullscreen().catch(() => setFullscreenWarning(true));
      }
      if (startRes.resumed) toast.show("Resumed your in-progress attempt. Autosave continues from here.", "info");
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
      await apiFetch(`/exams/attempts/${attempt.attempt_id}/autosave`, { method: "PUT", body: JSON.stringify({ question_id: question.id, selected_option_ids: next }) });
      setSavedAt(new Date());
    } catch {
      toast.show("Autosave failed — stay connected until you submit.", "error");
    }
  };

  const toggleFlag = (questionId: string) => {
    setFlagged((prev) => {
      const next = new Set(prev);
      if (next.has(questionId)) next.delete(questionId); else next.add(questionId);
      return next;
    });
  };

  const jumpTo = (index: number) => {
    setCurrentIndex(index);
    const id = questions?.[index]?.id;
    const node = id ? questionRefs.current[id] : null;
    node?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  if (loading) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return <div className="mx-auto max-w-md px-6 py-24 text-center"><p className="text-fg-muted">Sign in to take this exam.</p><Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link></div>;
  }

  if (result) {
    return <div className="mx-auto max-w-lg px-6 py-16 text-center"><div className={`card ${result.passed ? "border-emerald-500/40" : "border-amber-500/40"}`}><p className="text-sm uppercase tracking-widest text-fg-subtle">Exam complete</p><p className="mt-2 text-4xl font-bold text-fg">{result.score_percent ?? 0}%</p><p className="mt-2 text-sm text-fg-muted">{result.points_earned} / {result.points_possible} points · {result.passed ? "Passed" : "Not passed"}</p><div className="mt-6 flex justify-center gap-3"><Link href="/dashboard" className="btn-secondary">Dashboard</Link><button onClick={() => router.push(`/exams/${params.id}/review`)} className="btn-primary">Review answers</button></div></div></div>;
  }

  const attemptedCount = questions ? questions.filter((q) => (answers[q.id] || []).length > 0).length : 0;
  const flaggedCount = flagged.size;
  const totalSeconds = meta?.time_limit_seconds || 1;
  const currentQuestion = questions?.[currentIndex];

  return (
    <ExamIntegrityGuard enabled={Boolean(attempt && meta?.integrity_monitoring_enabled)} fullscreenRequired={Boolean(meta?.fullscreen_required)} onIntegrityEvent={reportIntegrityEvent}>
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <header className="sticky top-0 z-20 mb-6 border-b border-ink-700/70 bg-bg/95 py-3 backdrop-blur">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0"><h1 className="truncate text-xl font-bold text-fg sm:text-2xl">{meta?.title || "Exam"}</h1><p className="text-xs text-fg-subtle">{attemptedCount}/{questions?.length || 0} answered{flaggedCount ? ` · ${flaggedCount} flagged` : ""} {savedAt ? `· Saved ${savedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}` : ""}</p></div>
            <div className="flex items-center gap-3"><div className="hidden text-right sm:block"><p className="text-[10px] uppercase tracking-[0.2em] text-fg-subtle">Time left</p><p className="font-mono text-sm text-fg">{formatDuration(remaining)}</p></div><TimerRing remaining={remaining} total={totalSeconds} /></div>
          </div>
          {attempt && <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-ink-800"><div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${questions?.length ? (attemptedCount / questions.length) * 100 : 0}%` }} /></div>}
        </header>

        {error && <p className="mb-4 text-sm text-red-700 dark:text-red-400">{error}</p>}

        {!attempt || !questions ? (
          <div className="mx-auto max-w-2xl card text-center"><p className="text-sm text-fg-muted">This is a timed exam. Answers autosave as you go. Integrity events such as tab changes, leaving fullscreen, copy/paste, and right-click are recorded for review.</p>{meta?.fullscreen_required && <p className="mt-3 text-xs text-fg-subtle">Fullscreen is required. Your attempt will remain server-timed even if the browser changes state.</p>}<button onClick={start} disabled={starting} className="btn-primary mt-6">{starting ? "Starting…" : "Start exam"}</button></div>
        ) : (
          <div className="grid gap-6 lg:grid-cols-[15rem_minmax(0,1fr)] xl:grid-cols-[17rem_minmax(0,1fr)]">
            <aside className="hidden lg:block lg:sticky lg:top-24 lg:self-start"><div className="card p-4"><div className="flex items-center justify-between"><p className="text-xs font-semibold uppercase tracking-widest text-fg-subtle">Questions</p><span className="text-xs text-fg-muted">{attemptedCount}/{questions.length}</span></div><div className="mt-4 grid grid-cols-5 gap-2">{questions.map((q, index) => { const answered = (answers[q.id] || []).length > 0; const isCurrent = index === currentIndex; const isFlagged = flagged.has(q.id); return <button key={q.id} onClick={() => jumpTo(index)} className={`relative flex h-9 w-9 items-center justify-center border text-xs font-semibold transition ${isCurrent ? "border-brand-500 text-brand-600 dark:text-brand-400" : answered ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-600" : "border-ink-700 text-fg-muted"}`}>{index + 1}{isFlagged && <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-amber-400" />}</button>; })}</div><div className="mt-4 border-t border-ink-700 pt-4 text-xs text-fg-subtle"><p>Green = answered</p><p>Amber dot = flagged</p><p>Border = current</p></div></div></aside>

            <main className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-3 border border-ink-700 bg-bg/70 px-4 py-3 text-xs"><span className="text-fg-muted">Question {currentIndex + 1} of {questions.length}</span><div className="flex items-center gap-3"><button onClick={() => setShowSummary(true)} className="btn-secondary px-3 py-1.5">Review summary</button><span className="text-fg-subtle">{savedAt ? "Autosaved" : "Autosaving…"}</span></div></div>

              {questions.map((q, idx) => <div key={q.id} ref={(node) => { questionRefs.current[q.id] = node; }} className={`border bg-bg/70 p-5 transition sm:p-7 ${idx === currentIndex ? "border-brand-500/60 shadow-lg" : "border-ink-700/70"}`}>
                <div className="flex items-start justify-between gap-4"><p className="font-medium leading-7 text-fg">{idx + 1}. {q.prompt}</p><button onClick={() => toggleFlag(q.id)} className={`shrink-0 text-xs font-semibold ${flagged.has(q.id) ? "text-amber-500" : "text-fg-subtle hover:text-fg"}`}>{flagged.has(q.id) ? "Flagged" : "Flag for review"}</button></div>
                <div className="mt-5 space-y-2">{q.options.map((opt) => { const selected = (answers[q.id] || []).includes(opt.id); return <label key={opt.id} className={`flex cursor-pointer items-start gap-3 border px-4 py-3 text-sm transition ${selected ? "border-brand-500 bg-brand-500/10 text-brand-700 dark:text-white" : "border-ink-700 text-fg-muted hover:border-ink-500"}`}><input type={q.question_type === "multiple" ? "checkbox" : "radio"} name={q.id} checked={selected} onChange={() => toggleOption(q, opt.id)} className="mt-1 accent-brand-500" /><span>{opt.text}</span></label>; })}</div>
                <div className="mt-5 flex items-center justify-between border-t border-ink-700 pt-4 text-xs text-fg-subtle"><button onClick={() => jumpTo(Math.max(0, idx - 1))} disabled={idx === 0} className="disabled:opacity-40">← Previous</button><span>{q.points} {q.points === 1 ? "point" : "points"}</span><button onClick={() => jumpTo(Math.min(questions.length - 1, idx + 1))} disabled={idx === questions.length - 1} className="disabled:opacity-40">Next →</button></div>
              </div>)}

              <button onClick={() => setShowSummary(true)} disabled={submitting} className="btn-primary w-full">{submitting ? "Submitting…" : "Review and submit exam"}</button>
            </main>
          </div>
        )}

        {fullscreenWarning && attempt && meta?.fullscreen_required && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-6 backdrop-blur-sm"><div className="max-w-md border border-brand-500/40 bg-bg p-6 text-center shadow-2xl"><p className="text-xs uppercase tracking-[0.25em] text-brand-500">Exam paused</p><h2 className="mt-2 text-xl font-bold text-fg">Return to fullscreen</h2><p className="mt-2 text-sm text-fg-muted">Fullscreen was exited and the event was logged. Re-enter fullscreen to continue.</p><button onClick={() => document.documentElement.requestFullscreen?.().then(() => setFullscreenWarning(false)).catch(() => {})} className="btn-primary mt-6">Re-enter fullscreen</button></div></div>}

        {showSummary && questions && <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"><div className="max-h-[85vh] w-full max-w-2xl overflow-auto border border-ink-700 bg-bg p-5 shadow-2xl sm:p-7"><div className="flex items-center justify-between gap-4"><div><p className="text-xs uppercase tracking-widest text-fg-subtle">Before you submit</p><h2 className="mt-1 text-2xl font-bold text-fg">Exam summary</h2></div><button onClick={() => setShowSummary(false)} className="text-fg-subtle hover:text-fg">Close</button></div><div className="mt-5 grid gap-3 sm:grid-cols-3"><div className="border border-ink-700 p-4"><p className="text-xs text-fg-subtle">Answered</p><p className="mt-1 text-2xl font-bold text-emerald-500">{attemptedCount}</p></div><div className="border border-ink-700 p-4"><p className="text-xs text-fg-subtle">Unanswered</p><p className="mt-1 text-2xl font-bold text-fg">{questions.length - attemptedCount}</p></div><div className="border border-ink-700 p-4"><p className="text-xs text-fg-subtle">Flagged</p><p className="mt-1 text-2xl font-bold text-amber-500">{flaggedCount}</p></div></div><div className="mt-5 grid grid-cols-5 gap-2 sm:grid-cols-10">{questions.map((q, idx) => <button key={q.id} onClick={() => { setShowSummary(false); jumpTo(idx); }} className={`border px-2 py-2 text-xs ${flagged.has(q.id) ? "border-amber-500 text-amber-500" : (answers[q.id] || []).length ? "border-emerald-500/50 text-emerald-500" : "border-ink-700 text-fg-muted"}`}>{idx + 1}</button>)}</div><div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button onClick={() => setShowSummary(false)} className="btn-secondary">Continue exam</button><button onClick={() => void doSubmit()} disabled={submitting} className="btn-primary">{submitting ? "Submitting…" : "Submit final answer"}</button></div></div></div>}
      </div>
    </ExamIntegrityGuard>
  );
}
