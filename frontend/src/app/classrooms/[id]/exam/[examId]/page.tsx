"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";
import { PageLoader } from "@/components/PageLoader";
import { ExamIntegrityGuard } from "@/components/exams/ExamIntegrityGuard";
import { ExamSecurityShell } from "@/components/exams/ExamSecurityShell";

interface ExamInfo {
  id: string; classroom_id: string; title: string; description: string;
  question_count: number; duration_seconds: number;
  starts_at: string | null; ends_at: string | null; status: string;
  fullscreen_required: boolean; integrity_monitoring_enabled: boolean;
  max_warnings_before_terminate: number;
}
interface Option { id: string; text: string; order_index: number; }
interface Question { id: string; prompt: string; question_type: string; points: number; options: Option[]; }
interface AttemptStart { attempt_id: string; server_deadline_at: string; remaining_seconds: number; }
interface AttemptResult {
  id: string; score_percent: number | null; points_earned: number | null;
  points_possible: number | null; status: string;
}

export default function ClassroomExamPage() {
  const { id: classroomId, examId } = useParams<{ id: string; examId: string }>();
  const router = useRouter();
  const { user } = useAuth();

  const [exam, setExam] = useState<ExamInfo | null>(null);
  const [phase, setPhase] = useState<"loading" | "info" | "security" | "exam" | "submitted" | "error">("loading");
  const [error, setError] = useState("");
  const [attemptId, setAttemptId] = useState("");
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [currentIdx, setCurrentIdx] = useState(0);
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [deviceFp, setDeviceFp] = useState("");
  const timerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  useEffect(() => {
    if (!examId || !classroomId) return;
    apiFetch<ExamInfo[]>(`/classrooms/${classroomId}/exams`)
      .then(exams => {
        const found = exams.find(e => e.id === examId);
        if (found) { setExam(found); setPhase("info"); }
        else setPhase("error");
      })
      .catch(() => setPhase("error"));
  }, [examId, classroomId]);

  const startAttempt = async () => {
    try {
      const res = await apiFetch<AttemptStart>(`/classrooms/${classroomId}/exams/${examId}/attempts`, { method: "POST" });
      setAttemptId(res.attempt_id);
      setRemainingSeconds(res.remaining_seconds);
      const qs = await apiFetch<Question[]>(`/classrooms/exams/attempts/${res.attempt_id}/questions`);
      setQuestions(qs);
      setPhase("exam");
    } catch (err: any) {
      setError(err?.message || "Failed to start exam.");
      setPhase("error");
    }
  };

  const handleSecurityReady = (fp: string) => {
    setDeviceFp(fp);
    startAttempt();
  };

  const toggleOption = (questionId: string, optionId: string, questionType: string) => {
    setAnswers(prev => {
      const current = prev[questionId] || [];
      if (questionType === "single" || questionType === "true_false") {
        return { ...prev, [questionId]: [optionId] };
      }
      if (current.includes(optionId)) {
        return { ...prev, [questionId]: current.filter(id => id !== optionId) };
      }
      return { ...prev, [questionId]: [...current, optionId] };
    });
  };

  const handleSubmit = useCallback(async () => {
    if (submitting || !attemptId) return;
    setSubmitting(true);
    clearInterval(timerRef.current);
    try {
      const payload = questions.map(q => ({
        question_id: q.id,
        selected_option_ids: answers[q.id] || [],
      }));
      const res = await apiFetch<AttemptResult>(`/classrooms/exams/attempts/${attemptId}/submit`, {
        method: "POST",
        body: JSON.stringify({ answers: payload }),
      });
      setResult(res);
      setPhase("submitted");
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    } catch (err: any) {
      setError(err?.message || "Submit failed.");
      setPhase("error");
    }
  }, [submitting, attemptId, questions, answers]);

  const hasTimeLeft = remainingSeconds > 0;
  useEffect(() => {
    if (!hasTimeLeft || phase !== "exam") return;
    timerRef.current = setInterval(() => {
      setRemainingSeconds(prev => {
        if (prev <= 1) { handleSubmit(); return 0; }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, [phase, hasTimeLeft, handleSubmit]);

  const reportEvent = useCallback(async (eventType: string) => {
    if (!attemptId) return;
    try {
      const res = await apiFetch<{ terminated?: boolean }>(`/classrooms/exams/attempts/${attemptId}/events`, {
        method: "PUT",
        body: JSON.stringify({ event_type: eventType, device_fingerprint: deviceFp }),
      });
      if (res.terminated) {
        setResult({ id: attemptId, score_percent: null, points_earned: null, points_possible: null, status: "terminated" });
        setPhase("submitted");
        if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
      }
    } catch { /* best-effort */ }
  }, [attemptId, deviceFp]);

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  if (phase === "loading") return <div className="mx-auto max-w-4xl px-6 py-16"><PageLoader size="md" /></div>;

  if (phase === "error") {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">{error || "Something went wrong."}</p>
        <button onClick={() => router.back()} className="btn-secondary mt-6">Go back</button>
      </div>
    );
  }

  if (phase === "info" && exam) {
    return (
      <div className="mx-auto max-w-lg px-6 py-16">
        <h1 className="text-2xl font-bold text-fg">{exam.title}</h1>
        <p className="mt-2 text-sm text-fg-muted">{exam.description}</p>
        <div className="mt-6 space-y-2 text-sm text-fg-subtle">
          <p>{exam.question_count} questions · {Math.round(exam.duration_seconds / 60)} minutes</p>
          {exam.starts_at && <p>Opens: {new Date(exam.starts_at).toLocaleString()}</p>}
          {exam.ends_at && <p>Closes: {new Date(exam.ends_at).toLocaleString()}</p>}
        </div>
        {exam.status === "open" ? (
          <button onClick={() => setPhase("security")} className="btn-primary mt-8 w-full">Start Exam</button>
        ) : exam.status === "scheduled" ? (
          <p className="mt-8 text-center text-sm text-amber-400">This exam hasn&apos;t opened yet.</p>
        ) : (
          <p className="mt-8 text-center text-sm text-fg-subtle">This exam is closed.</p>
        )}
      </div>
    );
  }

  if (phase === "security" && exam) {
    return (
      <ExamSecurityShell fullscreenRequired={exam.fullscreen_required} onReady={handleSecurityReady}>
        <div />
      </ExamSecurityShell>
    );
  }

  if (phase === "submitted") {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        {result?.status === "terminated" ? (
          <>
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-500/10 text-3xl text-red-400">✕</div>
            <h2 className="text-xl font-bold text-fg">Exam Terminated</h2>
            <p className="mt-2 text-sm text-fg-muted">Your exam was terminated due to integrity violations.</p>
          </>
        ) : (
          <>
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10 text-3xl text-emerald-400">✓</div>
            <h2 className="text-xl font-bold text-fg">Exam Submitted</h2>
            {result?.score_percent != null && (
              <p className="mt-3 text-3xl font-bold text-brand-600 dark:text-brand-400">{result.score_percent}%</p>
            )}
            {result?.points_earned != null && result?.points_possible != null && (
              <p className="mt-1 text-sm text-fg-muted">{result.points_earned} / {result.points_possible} points</p>
            )}
          </>
        )}
        <button onClick={() => router.push(`/classrooms/${classroomId}`)} className="btn-primary mt-8">Back to Classroom</button>
      </div>
    );
  }

  if (phase !== "exam" || questions.length === 0) return null;
  const q = questions[currentIdx];
  const selected = answers[q.id] || [];
  const isMulti = q.question_type === "multiple";

  return (
    <ExamIntegrityGuard
      enabled={exam?.integrity_monitoring_enabled ?? true}
      fullscreenRequired={exam?.fullscreen_required ?? true}
      maxWarnings={exam?.max_warnings_before_terminate ?? 2}
      onIntegrityEvent={reportEvent}
      onTerminate={handleSubmit}
    >
      <div className="min-h-screen bg-ink-950">
        <div className="sticky top-0 z-30 flex items-center justify-between border-b border-ink-700 bg-ink-950 px-4 py-3">
          <span className="text-sm font-medium text-fg">
            Question {currentIdx + 1} of {questions.length}
          </span>
          <span className={`rounded-full px-3 py-1 text-sm font-mono font-bold ${remainingSeconds < 60 ? "bg-red-500/20 text-red-400" : "bg-ink-800 text-fg"}`}>
            {formatTime(remainingSeconds)}
          </span>
        </div>

        <div className="mx-auto max-w-2xl px-6 py-8">
          <div className="flex gap-2 overflow-x-auto pb-4">
            {questions.map((_, i) => (
              <button
                key={i}
                onClick={() => setCurrentIdx(i)}
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xs font-medium transition ${
                  i === currentIdx
                    ? "bg-brand-600 text-white"
                    : answers[questions[i].id]?.length
                      ? "bg-emerald-500/20 text-emerald-400"
                      : "bg-ink-800 text-fg-muted hover:bg-ink-700"
                }`}
              >
                {i + 1}
              </button>
            ))}
          </div>

          <div className="card mt-4">
            <div className="flex items-start justify-between gap-2">
              <p className="text-fg">{q.prompt}</p>
              <span className="shrink-0 text-xs text-fg-subtle">{q.points} pt{q.points !== 1 ? "s" : ""}</span>
            </div>
            {isMulti && (
              <p className="mt-2 text-xs text-brand-400">Select all that apply</p>
            )}
            <div className="mt-4 space-y-2">
              {q.options.map(o => {
                const isSelected = selected.includes(o.id);
                return (
                  <button
                    key={o.id}
                    onClick={() => toggleOption(q.id, o.id, q.question_type)}
                    className={`flex w-full items-center gap-3 rounded-lg border px-4 py-3 text-left text-sm transition ${
                      isSelected
                        ? "border-brand-500 bg-brand-500/10 text-fg"
                        : "border-ink-700 text-fg-muted hover:border-ink-600 hover:text-fg"
                    }`}
                  >
                    <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded${isMulti ? "" : "-full"} border ${
                      isSelected ? "border-brand-500 bg-brand-500 text-white" : "border-ink-600"
                    }`}>
                      {isSelected && (isMulti ? "✓" : "●")}
                    </span>
                    {o.text}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="mt-6 flex items-center justify-between">
            <button
              onClick={() => setCurrentIdx(i => Math.max(0, i - 1))}
              disabled={currentIdx === 0}
              className="btn-secondary disabled:opacity-30"
            >
              Previous
            </button>
            {currentIdx < questions.length - 1 ? (
              <button onClick={() => setCurrentIdx(i => i + 1)} className="btn-primary">
                Next
              </button>
            ) : (
              <button onClick={handleSubmit} disabled={submitting} className="btn-primary !bg-emerald-600 hover:!bg-emerald-500 disabled:opacity-50">
                {submitting ? "Submitting..." : "Submit Exam"}
              </button>
            )}
          </div>
        </div>
      </div>
    </ExamIntegrityGuard>
  );
}
