"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { PageLoader } from "@/components/PageLoader";
import { ExamIntegrityGuard } from "@/components/exams/ExamIntegrityGuard";
import { ExamSecurityShell } from "@/components/exams/ExamSecurityShell";
import { setExamChromeHidden } from "@/lib/useFullscreen";

// @vladmandic/face-api touches browser-only globals at module-evaluation
// time, not just when its functions are called -- see the matching note on
// contests/[id]/page.tsx and elimination/[battleId]/page.tsx (React error
// #419, confirmed live). Dynamic + ssr:false keeps it out of the server render.
const FaceProctor = dynamic(() => import("@/components/exams/FaceProctor").then((m) => m.FaceProctor), { ssr: false });

interface ExamInfo {
  id: string; classroom_id: string; title: string; description: string;
  question_count: number; duration_seconds: number;
  starts_at: string | null; ends_at: string | null; status: string;
  fullscreen_required: boolean; integrity_monitoring_enabled: boolean;
  max_warnings_before_terminate: number; face_proctoring_required: boolean;
}
interface Option { id: string; text: string; order_index: number; }
interface Question { id: string; prompt: string; question_type: string; points: number; options: Option[]; }
interface AttemptStart {
  attempt_id: string; status: "waiting" | "in_progress";
  exam_starts_at: string; server_deadline_at: string;
  seconds_until_start: number; remaining_seconds: number;
}
interface MyAttempt {
  attempt_id: string; status: "waiting" | "in_progress" | "submitted" | "terminated";
  exam_starts_at: string; server_deadline_at: string;
  seconds_until_start: number; remaining_seconds: number;
  score_percent: number | null; points_earned: number | null; points_possible: number | null;
}
interface AttemptResult {
  id: string; score_percent: number | null; points_earned: number | null;
  points_possible: number | null; status: string;
}

export default function ClassroomExamPage() {
  const { id: classroomId, examId } = useParams<{ id: string; examId: string }>();
  const router = useRouter();
  const { user } = useAuth();

  const [exam, setExam] = useState<ExamInfo | null>(null);
  const [phase, setPhase] = useState<"loading" | "info" | "security" | "waiting" | "exam" | "submitted" | "error">("loading");
  const [error, setError] = useState("");
  const [attemptId, setAttemptId] = useState("");
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [currentIdx, setCurrentIdx] = useState(0);
  const [secondsUntilStart, setSecondsUntilStart] = useState(0);
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [deviceFp, setDeviceFp] = useState("");
  const [cameraDenied, setCameraDenied] = useState(false);
  const [cameraDeniedReported, setCameraDeniedReported] = useState(false);
  // exam.status only ever reflects what the host set it to at publish time
  // ("open" if published after starts_at, "scheduled" if published before)
  // -- nothing updates it later, by design (see start_attempt's docstring:
  // whether joining/the exam itself is actually open is answered purely by
  // comparing `now` against starts_at/ends_at, same as the backend does).
  // Gating the "Join Exam" button on a literal status==="open" check was a
  // leftover from before that redesign: an exam published early (the
  // ordinary case — a host publishes ahead of the window, not at the exact
  // instant it opens) stayed "scheduled" forever, so the button never
  // appeared even once the real joining window had opened. Ticking `now`
  // here instead lets the page reflect the real, current window without
  // requiring a manual refresh right as it opens.
  const [now, setNow] = useState(() => Date.now());
  const timerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const waitTimerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  useEffect(() => {
    if (phase !== "info") return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [phase]);

  // Hides the site header/footer for the whole locked-down stretch, not
  // just while the browser happens to be in real fullscreen -- fullscreen
  // can fail to engage for reasons outside this app's control (a blocked
  // permission, browser policy, a lost user-gesture context), and when
  // that happens the exam is still genuinely running and the header is
  // still exactly as much of a problem (dead space, and a way out of a
  // supposedly locked-down exam via its nav links).
  useEffect(() => {
    const hidden = phase === "security" || phase === "waiting" || phase === "exam";
    setExamChromeHidden(hidden);
    return () => setExamChromeHidden(false);
  }, [phase]);

  // Joining and taking the exam are different moments: everyone who joins gets
  // the exam's full duration starting from the SAME instant (when joining
  // closes), so a student who joins seconds before the deadline isn't
  // shortchanged relative to one who joined when it opened. If that instant is
  // still in the future, this drops into a waiting-room phase with its own
  // countdown instead of fetching questions immediately.
  const fetchQuestions = useCallback(async (attId: string) => {
    try {
      const qs = await apiFetch<Question[]>(`/classrooms/exams/attempts/${attId}/questions`);
      setQuestions(qs);
      setPhase("exam");
    } catch (err) {
      // A slightly-early request (clock skew between browser and server) is
      // expected right at the boundary -- the waiting-room countdown will
      // retry a moment later rather than surfacing this as a real failure.
      if (err instanceof ApiError && err.code === "exam_not_started") return;
      setError(err instanceof ApiError ? err.message : "Failed to load questions.");
      setPhase("error");
    }
  }, []);

  useEffect(() => {
    if (!examId || !classroomId) return;
    apiFetch<ExamInfo[]>(`/classrooms/${classroomId}/exams`)
      .then(async exams => {
        const found = exams.find(e => e.id === examId);
        if (!found) { setPhase("error"); return; }
        setExam(found);

        // A fresh page load (or a refresh mid-exam, or revisiting after
        // finishing) has no way to know whether this student already has
        // an attempt -- without checking, a submitted student saw the same
        // generic "join/closed" screen as someone who never attempted it,
        // with their real score nowhere in sight.
        try {
          const mine = await apiFetch<MyAttempt | null>(`/classrooms/${classroomId}/exams/${examId}/attempts/me`);
          if (mine) {
            if (mine.status === "submitted" || mine.status === "terminated") {
              setResult({ id: mine.attempt_id, score_percent: mine.score_percent, points_earned: mine.points_earned, points_possible: mine.points_possible, status: mine.status });
              setPhase("submitted");
              return;
            }
            // Still going (waiting or in_progress) -- deliberately NOT
            // jumped straight into, even though the attempt already exists.
            // Route through the security shell every time, the exact same
            // path a fresh join takes, so fullscreen and the camera are
            // actually (re-)confirmed THIS session before any question is
            // shown -- a student who alt-tabbed away, closed the tab, or
            // reloaded mid-exam must not land back in live questions with
            // no fullscreen and no camera check just because an attempt
            // row already exists. startAttempt()'s POST is idempotent for
            // an existing attempt (see start_attempt's backend docstring),
            // so this resumes into exactly the right waiting/in_progress
            // state once the shell's fullscreen/camera gate is cleared.
            setPhase("security");
            return;
          }
        } catch {
          // No existing attempt (or a transient failure reading it) --
          // fall through to the normal join screen below.
        }
        setPhase("info");
      })
      .catch(() => setPhase("error"));
  }, [examId, classroomId, fetchQuestions]);

  const startAttempt = async () => {
    try {
      const res = await apiFetch<AttemptStart>(`/classrooms/${classroomId}/exams/${examId}/attempts`, { method: "POST" });
      setAttemptId(res.attempt_id);
      if (res.status === "waiting") {
        setSecondsUntilStart(res.seconds_until_start);
        setPhase("waiting");
      } else {
        setRemainingSeconds(res.remaining_seconds);
        await fetchQuestions(res.attempt_id);
      }
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

  useEffect(() => {
    if (phase !== "waiting") return;
    waitTimerRef.current = setInterval(() => {
      setSecondsUntilStart(prev => {
        if (prev <= 1) {
          setRemainingSeconds(exam?.duration_seconds ?? 0);
          fetchQuestions(attemptId);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(waitTimerRef.current);
  }, [phase, attemptId, exam?.duration_seconds, fetchQuestions]);

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
    const startsAtMs = exam.starts_at ? new Date(exam.starts_at).getTime() : null;
    const endsAtMs = exam.ends_at ? new Date(exam.ends_at).getTime() : null;
    const notYetPublished = exam.status === "draft";
    const closedForGood = exam.status === "closed" || (endsAtMs !== null && now > endsAtMs);
    const joiningNotYetOpen = !notYetPublished && !closedForGood && startsAtMs !== null && now < startsAtMs;
    const canJoin = !notYetPublished && !closedForGood && !joiningNotYetOpen;

    return (
      <div className="mx-auto max-w-lg px-6 py-16">
        <h1 className="text-2xl font-bold text-fg">{exam.title}</h1>
        <p className="mt-2 text-sm text-fg-muted">{exam.description}</p>
        <div className="mt-6 space-y-2 text-sm text-fg-subtle">
          <p>{exam.question_count} questions · {Math.round(exam.duration_seconds / 60)} minutes once it starts</p>
          {exam.starts_at && <p>Joining opens: {new Date(exam.starts_at).toLocaleString()}</p>}
          {exam.ends_at && <p>Joining closes: {new Date(exam.ends_at).toLocaleString()}</p>}
          {exam.ends_at && (
            <p className="text-fg-subtle/80">
              The exam begins for everyone the moment joining closes — join any time before then and you&apos;ll still get the full {Math.round(exam.duration_seconds / 60)} minutes.
            </p>
          )}
        </div>
        {canJoin ? (
          <button onClick={() => setPhase("security")} className="btn-primary mt-8 w-full">Join Exam</button>
        ) : notYetPublished ? (
          <p className="mt-8 text-center text-sm text-fg-subtle">This exam hasn&apos;t been published yet.</p>
        ) : joiningNotYetOpen ? (
          <p className="mt-8 text-center text-sm text-amber-400">
            Joining opens {exam.starts_at && new Date(exam.starts_at).toLocaleString()} — check back then.
          </p>
        ) : (
          <p className="mt-8 text-center text-sm text-fg-subtle">This exam is closed.</p>
        )}
      </div>
    );
  }

  if (phase === "security" && exam) {
    return (
      <ExamSecurityShell fullscreenRequired={exam.fullscreen_required} faceProctoringRequired={exam.face_proctoring_required} onReady={handleSecurityReady}>
        <div />
      </ExamSecurityShell>
    );
  }

  if (phase === "waiting") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-ink-950 px-4 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-brand-500/10 text-2xl">⏳</div>
        <h1 className="text-xl font-bold text-fg">You&apos;re in</h1>
        <p className="mt-2 max-w-sm text-sm text-fg-muted">
          The exam starts automatically for everyone once joining closes. Stay on this page — it&apos;ll begin on its own.
        </p>
        <p className="mt-6 font-mono text-4xl font-bold text-fg">{formatTime(secondsUntilStart)}</p>
        <p className="mt-1 text-xs text-fg-subtle">until the exam begins</p>
      </div>
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

        {exam?.face_proctoring_required && cameraDenied && (
          <p className="mx-auto mt-4 max-w-2xl rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-2.5 text-xs text-red-700 dark:text-red-400">
            Camera access is required for this exam. Please allow camera permission and reload the page to continue.
          </p>
        )}
        <FaceProctor
          enabled={!!exam?.face_proctoring_required}
          onProctorEvent={reportEvent}
          onCameraReady={() => setCameraDenied(false)}
          onCameraDenied={() => {
            setCameraDenied(true);
            if (!cameraDeniedReported) {
              setCameraDeniedReported(true);
              reportEvent("no_face_detected");
            }
          }}
        />

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
