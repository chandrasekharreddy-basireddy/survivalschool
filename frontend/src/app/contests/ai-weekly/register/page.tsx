"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatDateTime } from "@/lib/format";

interface Subject { id: string; name: string; slug: string }
interface Topic { id: string; name: string; slug: string }
interface RegistrationStatus { is_open: boolean; next_open_at: string | null; message: string }
interface TopicDifficulty { topic_id: string; difficulty_percent: number; reason: string; sample_size: number; eligible_for_ai_exam: boolean }
interface RegisterResult { attempt_id: string; contest_id: string; contest_title: string; starts_at: string; ends_at: string; status: string }

export default function AiWeeklyRegisterPage() {
  const { user, loading } = useAuth();
  const toast = useToast();

  const [status, setStatus] = useState<RegistrationStatus | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [subjectId, setSubjectId] = useState("");
  const [topicId, setTopicId] = useState("");
  const [difficulty, setDifficulty] = useState<TopicDifficulty | null>(null);
  const [checkingDifficulty, setCheckingDifficulty] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [result, setResult] = useState<RegisterResult | null>(null);

  useEffect(() => {
    apiFetch<RegistrationStatus>("/contests/ai-weekly/registration-status", { auth: false }).then(setStatus).catch(() => setStatus(null));
    apiFetch<Subject[]>("/subjects", { auth: false }).then(setSubjects).catch(() => setSubjects([]));
  }, []);

  useEffect(() => {
    if (!subjectId) { setTopics([]); setTopicId(""); return; }
    apiFetch<Topic[]>(`/subjects/${subjectId}/topics`, { auth: false }).then(setTopics).catch(() => setTopics([]));
    setTopicId("");
    setDifficulty(null);
  }, [subjectId]);

  useEffect(() => {
    if (!topicId) { setDifficulty(null); return; }
    setCheckingDifficulty(true);
    apiFetch<TopicDifficulty>(`/topics/${topicId}/difficulty`)
      .then(setDifficulty)
      .catch(() => setDifficulty(null))
      .finally(() => setCheckingDifficulty(false));
  }, [topicId]);

  const register = async () => {
    if (!subjectId || !topicId) return;
    setRegistering(true);
    try {
      const res = await apiFetch<RegisterResult>("/contests/ai-weekly/register", {
        method: "POST",
        body: JSON.stringify({ subject_id: subjectId, topic_id: topicId }),
      });
      setResult(res);
      toast.show("You're registered for the AI Weekly Exam.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't register.", "error");
    } finally {
      setRegistering(false);
    }
  };

  if (loading) return <div className="mx-auto max-w-2xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to register for the AI Weekly Exam.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">AI Weekly Exam — register</h1>
      <p className="mt-1 text-sm text-fg-muted">
        A fixed-format, 2-hour exam — 40 single-answer and 10 multi-select questions, everyone completes the full
        exam (no elimination). Certificates go to the top 3 finishers. Registration opens every Thursday (IST).
      </p>

      {status && (
        <div className={`card mt-6 !p-4 ${status.is_open ? "border-emerald-500/40" : "border-amber-500/40"}`}>
          <p className={`text-sm font-medium ${status.is_open ? "text-emerald-700 dark:text-emerald-400" : "text-amber-700 dark:text-amber-400"}`}>
            {status.message}
          </p>
          {!status.is_open && status.next_open_at && (
            <p className="mt-1 text-xs text-fg-subtle">Next window opens {formatDateTime(status.next_open_at)}.</p>
          )}
        </div>
      )}

      {result ? (
        <div className="card mt-6 text-center border-emerald-500/40">
          <p className="text-sm uppercase tracking-widest text-fg-subtle">Registered</p>
          <h2 className="mt-2 text-lg font-semibold text-fg">{result.contest_title}</h2>
          <p className="mt-2 text-sm text-fg-muted">
            Starts {formatDateTime(result.starts_at)} · ends {formatDateTime(result.ends_at)}
          </p>
          <Link href={`/contests/${result.contest_id}`} className="btn-primary mt-4 inline-flex">View exam</Link>
        </div>
      ) : (
        <div className="card mt-6">
          <label className="text-sm font-medium text-fg">Subject</label>
          <select className="input mt-1.5" value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
            <option value="">Choose a subject…</option>
            {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>

          <label className="mt-4 block text-sm font-medium text-fg">Topic</label>
          <select className="input mt-1.5" value={topicId} onChange={(e) => setTopicId(e.target.value)} disabled={!subjectId}>
            <option value="">Choose a topic…</option>
            {topics.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>

          {checkingDifficulty && <p className="mt-3 text-xs text-fg-subtle">Checking eligibility…</p>}
          {difficulty && (
            <div className={`mt-4 rounded-lg border px-3 py-2.5 text-sm ${difficulty.eligible_for_ai_exam ? "border-emerald-500/40 text-emerald-700 dark:text-emerald-400" : "border-red-500/40 text-red-700 dark:text-red-400"}`}>
              <p className="font-medium">
                {difficulty.eligible_for_ai_exam ? "Eligible" : "Not eligible yet"} — difficulty {difficulty.difficulty_percent}%
                {" "}(needs 70%+)
              </p>
              <p className="mt-1 text-xs text-fg-subtle">{difficulty.reason}</p>
            </div>
          )}

          <button
            onClick={register}
            disabled={registering || !status?.is_open || !topicId || !difficulty?.eligible_for_ai_exam}
            className="btn-primary mt-5 w-full"
          >
            {registering ? "Registering…" : "Register for this week's exam"}
          </button>
          {!status?.is_open && <p className="mt-2 text-center text-xs text-fg-subtle">Registration is closed right now — check back on Thursday.</p>}
        </div>
      )}
    </div>
  );
}
