"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatDateTime } from "@/lib/format";

interface RegistrationStatus { is_open: boolean; next_open_at: string | null; message: string }
interface RegisterResult { attempt_id: string; contest_id: string; contest_title: string; starts_at: string; ends_at: string; status: string }
interface Rejection { message: string; difficulty_percent?: number; is_appropriate_scope?: boolean; min_difficulty_percent?: number }
interface Profile { public_handle: string | null; institute: string | null }

export default function AiWeeklyRegisterPage() {
  const { user, loading } = useAuth();
  const toast = useToast();

  const [status, setStatus] = useState<RegistrationStatus | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [subject, setSubject] = useState("");
  const [topic, setTopic] = useState("");
  const [institute, setInstitute] = useState("");
  const [registering, setRegistering] = useState(false);
  const [result, setResult] = useState<RegisterResult | null>(null);
  const [rejection, setRejection] = useState<Rejection | null>(null);

  useEffect(() => {
    apiFetch<RegistrationStatus>("/contests/ai-weekly/registration-status", { auth: false }).then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    if (!user) return;
    apiFetch<Profile>("/users/me/profile").then((p) => { setProfile(p); setInstitute(p.institute || ""); }).catch(() => setProfile(null));
  }, [user]);

  const register = async () => {
    if (!subject.trim() || !topic.trim()) return;
    setRegistering(true);
    setRejection(null);
    try {
      const res = await apiFetch<RegisterResult>("/contests/ai-weekly/register", {
        method: "POST",
        body: JSON.stringify({ subject_name: subject.trim(), topic_name: topic.trim() }),
      });
      setResult(res);
      toast.show("You're registered for the AI Weekly Exam.", "success");
      // Best-effort: remember the institute for next time. Never blocks
      // registration itself if it fails.
      if (institute.trim() && institute.trim() !== (profile?.institute || "")) {
        apiFetch("/users/me/profile", { method: "PATCH", body: JSON.stringify({ institute: institute.trim() }) }).catch(() => {});
      }
    } catch (err) {
      if (err instanceof ApiError && err.code === "validation_error" && "difficulty_percent" in err.details) {
        setRejection({
          message: err.message,
          difficulty_percent: err.details.difficulty_percent as number,
          is_appropriate_scope: err.details.is_appropriate_scope as boolean,
          min_difficulty_percent: err.details.min_difficulty_percent as number,
        });
      } else {
        toast.show(err instanceof ApiError ? err.message : "Couldn't register.", "error");
      }
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
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="text-sm font-medium text-fg">Name</label>
              <p className="input mt-1.5 !bg-ink-800 text-fg-muted">{user.full_name}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-fg">Email</label>
              <p className="input mt-1.5 !bg-ink-800 text-fg-muted">{user.email}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-fg">Username</label>
              <p className="input mt-1.5 !bg-ink-800 text-fg-muted">
                {profile?.public_handle ? `@${profile.public_handle}` : (
                  <Link href="/settings" className="text-brand-600 underline dark:text-brand-400">Set a username in settings</Link>
                )}
              </p>
            </div>
            <div>
              <label className="text-sm font-medium text-fg">Institute <span className="font-normal text-fg-subtle">(optional)</span></label>
              <input className="input mt-1.5" placeholder="Your college/university" value={institute} onChange={(e) => setInstitute(e.target.value)} />
            </div>
          </div>

          <label className="mt-4 block text-sm font-medium text-fg">Subject</label>
          <input
            className="input mt-1.5"
            placeholder="e.g. Computer Science"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          />

          <label className="mt-4 block text-sm font-medium text-fg">Topic</label>
          <input
            className="input mt-1.5"
            placeholder="e.g. Graph Algorithms and Shortest Paths"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
          />
          <p className="mt-1.5 text-xs text-fg-subtle">
            Be specific — the AI checks that this is a real, well-scoped subtopic broad enough to support 50
            distinct questions, and rates how difficult that exam would be.
          </p>

          {rejection && (
            <div className="mt-4 rounded-lg border border-red-500/40 px-3 py-2.5 text-sm text-red-700 dark:text-red-400">
              <p className="font-medium">Not eligible yet</p>
              <p className="mt-1 text-xs text-fg-subtle">{rejection.message}</p>
              {rejection.difficulty_percent != null && (
                <p className="mt-1 text-xs text-fg-subtle">
                  Difficulty {rejection.difficulty_percent}% (needs {rejection.min_difficulty_percent ?? 70}%+)
                  {rejection.is_appropriate_scope === false ? " · topic scope too narrow or unclear" : ""}
                </p>
              )}
            </div>
          )}

          <button
            onClick={register}
            disabled={registering || !status?.is_open || !subject.trim() || !topic.trim()}
            className="btn-primary mt-5 w-full"
          >
            {registering ? "Checking with AI…" : "Register for this week's exam"}
          </button>
          {!status?.is_open && <p className="mt-2 text-center text-xs text-fg-subtle">Registration is closed right now — check back on Thursday.</p>}
        </div>
      )}
    </div>
  );
}
