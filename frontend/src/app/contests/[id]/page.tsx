"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatDateTime, formatDuration } from "@/lib/format";
import { ContestCountdown } from "@/components/ContestCountdown";
import { ExamIntegrityGuard } from "@/components/exams/ExamIntegrityGuard";

interface Contest {
  id: string; title: string; description: string; starts_at: string; ends_at: string;
  duration_seconds: number; top_n_awarded: number; status: string; question_count: number;
  fullscreen_required?: boolean; integrity_monitoring_enabled?: boolean;
}
interface OptionPublic { id: string; text: string; order_index: number }
interface QuestionPublic { id: string; prompt: string; question_type: string; points: number; options: OptionPublic[] }
interface LeaderboardEntry { rank: number; student_id: string; student_name: string; score_percent: number; time_taken_seconds: number | null }
interface ContestResult { id: string; status: string; score_percent: number | null; rank: number | null }

export default function ContestDetailPage() {
  const params = useParams<{ id: string }>();
  const { user, loading } = useAuth();
  const toast = useToast();

  const [contest, setContest] = useState<Contest | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [attemptId, setAttemptId] = useState<string | null>(null);
  const [deadline, setDeadline] = useState<string | null>(null);
  const [questions, setQuestions] = useState<QuestionPublic[] | null>(null);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [result, setResult] = useState<ContestResult | null>(null);
  const [alreadyCompeted, setAlreadyCompeted] = useState(false);
  const [joining, setJoining] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const loadLeaderboard = useCallback(() => {
    apiFetch<LeaderboardEntry[]>(`/contests/${params.id}/leaderboard`, { auth: false }).then(setLeaderboard).catch(() => {});
  }, [params.id]);

  useEffect(() => {
    apiFetch<Contest>(`/contests/${params.id}`, { auth: false }).then(setContest).catch(() => setContest(null));
    loadLeaderboard();
  }, [params.id, loadLeaderboard]);

  const join = async () => {
    setJoining(true);
    try {
      const start = await apiFetch<{ attempt_id: string; server_deadline_at: string; resumed: boolean }>(
        `/contests/${params.id}/attempts`, { method: "POST" }
      );
      setAttemptId(start.attempt_id);
      setDeadline(start.server_deadline_at);
      const qs = await apiFetch<QuestionPublic[]>(`/contests/attempts/${start.attempt_id}/questions`);
      setQuestions(qs);
      if (contest?.fullscreen_required && document.documentElement.requestFullscreen) {
        // Best-effort — some browsers/contexts refuse this without a more
        // direct user gesture, but the "join" click itself usually counts.
        document.documentElement.requestFullscreen().catch(() => {});
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setAlreadyCompeted(true);
      } else {
        toast.show(err instanceof ApiError ? err.message : "Couldn't join this contest.", "error");
      }
    } finally {
      setJoining(false);
    }
  };

  const reportIntegrityEvent = useCallback(
    (eventType: "tab_blur" | "fullscreen_exit" | "copy" | "paste" | "right_click") => {
      if (!attemptId) return;
      apiFetch<{ logged: boolean; violation_count: number; auto_submitted: boolean }>(
        `/contests/attempts/${attemptId}/events`, { method: "PUT", body: JSON.stringify({ event_type: eventType }) }
      )
        .then((res) => {
          if (res.auto_submitted) {
            toast.show("Too many integrity violations — your exam was automatically submitted.", "error");
            setResult({ id: attemptId, status: "submitted", score_percent: null, rank: null });
          }
        })
        .catch(() => {});
    },
    [attemptId, toast]
  );

  const toggleOption = (question: QuestionPublic, optionId: string) => {
    setAnswers((prev) => {
      if (question.question_type === "single" || question.question_type === "true_false") {
        return { ...prev, [question.id]: [optionId] };
      }
      const current = prev[question.id] || [];
      const next = current.includes(optionId) ? current.filter((o) => o !== optionId) : [...current, optionId];
      return { ...prev, [question.id]: next };
    });
  };

  const submit = async () => {
    if (!attemptId || !questions) return;
    setSubmitting(true);
    try {
      const res = await apiFetch<ContestResult>(`/contests/attempts/${attemptId}/submit`, {
        method: "POST",
        body: JSON.stringify({ answers: questions.map((q) => ({ question_id: q.id, selected_option_ids: answers[q.id] || [] })) }),
      });
      setResult(res);
      loadLeaderboard();
      toast.show("Submitted! Check the leaderboard for your placement.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't submit.", "error");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading || contest === null) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">{contest.title}</h1>
      <p className="mt-2 text-sm text-fg-muted">{contest.description}</p>
      <div className="mt-4 flex flex-wrap items-center gap-4">
        <ContestCountdown startsAt={contest.starts_at} endsAt={contest.ends_at} status={contest.status} />
        <span className="text-xs text-fg-subtle">
          {contest.question_count} questions · up to {formatDuration(contest.duration_seconds)} once you start · top {contest.top_n_awarded} win a certificate
        </span>
      </div>

      {result ? (
        <div className="card mt-6 text-center border-emerald-500/40">
          <p className="text-sm uppercase tracking-widest text-fg-subtle">Submitted</p>
          <p className="mt-2 text-4xl font-bold text-fg">{result.score_percent}%</p>
          <p className="mt-2 text-sm text-fg-muted">Final placement is confirmed once the contest window closes — check the leaderboard below.</p>
        </div>
      ) : alreadyCompeted ? (
        <div className="card mt-6 text-center text-sm text-fg-muted">You&apos;ve already competed in this contest — see the leaderboard below for your result.</div>
      ) : !user ? (
        <div className="card mt-6 text-center">
          <p className="text-sm text-fg-muted">Sign in to compete.</p>
          <Link href="/login" className="btn-primary mt-4 inline-flex">Sign in</Link>
        </div>
      ) : contest.status === "scheduled" ? (
        <div className="card mt-6 text-center text-sm text-fg-muted">This contest hasn&apos;t opened yet — come back when the countdown reaches zero.</div>
      ) : contest.status === "closed" ? (
        <div className="card mt-6 text-center text-sm text-fg-muted">This contest has closed.</div>
      ) : !questions ? (
        <div className="card mt-6 text-center">
          <p className="text-sm text-fg-muted">One attempt per student — once you start, the clock runs even if you leave.</p>
          <button onClick={join} disabled={joining} className="btn-primary mt-4">
            {joining ? "Joining…" : "Join contest"}
          </button>
        </div>
      ) : (
        <ExamIntegrityGuard
          enabled={!!contest.integrity_monitoring_enabled}
          fullscreenRequired={!!contest.fullscreen_required}
          onIntegrityEvent={reportIntegrityEvent}
        >
        <div className="mt-6 space-y-6">
          {deadline && <p className="text-xs text-fg-subtle">Your deadline: {formatDateTime(deadline)}</p>}
          {contest.integrity_monitoring_enabled && (
            <p className="rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
              This exam is integrity-monitored — leaving fullscreen, switching tabs, or copy/paste is logged and can auto-submit your attempt immediately, with no credit for anything left unanswered.
            </p>
          )}
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
                        name={q.id} checked={selected} onChange={() => toggleOption(q, opt.id)} className="accent-brand-500"
                      />
                      {opt.text}
                    </label>
                  );
                })}
              </div>
            </div>
          ))}
          <button onClick={submit} disabled={submitting} className="btn-primary w-full">
            {submitting ? "Submitting…" : "Submit final answers"}
          </button>
        </div>
        </ExamIntegrityGuard>
      )}

      <div className="mt-10">
        <h2 className="font-semibold text-fg">Leaderboard</h2>
        {leaderboard.length === 0 ? (
          <p className="mt-2 text-sm text-fg-subtle">No one has finished yet — be the first.</p>
        ) : (
          <ol className="mt-3 space-y-1.5">
            {leaderboard.map((e) => (
              <li key={e.student_id} className={`card !p-3 flex items-center justify-between text-sm ${e.rank <= contest.top_n_awarded ? "border-amber-500/40" : ""}`}>
                <span className="flex items-center gap-3">
                  <span className={`font-mono font-bold ${e.rank <= contest.top_n_awarded ? "text-amber-700 dark:text-amber-400" : "text-fg-subtle"}`}>#{e.rank}</span>
                  <span className="text-fg">{e.student_name}</span>
                </span>
                <span className="text-fg-muted">{e.score_percent}%</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
