"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";

interface ExamMeta { id: string; title: string }
interface FlaggedEvent { type: string; at: string }
interface FlaggedAttempt {
  attempt_id: string;
  student_id: string;
  student_name: string;
  status: string;
  score_percent: number | null;
  flagged_events: FlaggedEvent[];
}

const EVENT_LABELS: Record<string, string> = {
  tab_blur: "Left tab",
  fullscreen_exit: "Exited fullscreen",
  copy: "Copied text",
  paste: "Pasted text",
  right_click: "Right-clicked",
  late_submission: "Submitted after deadline",
};

export default function FlaggedAttemptsPage() {
  const params = useParams<{ id: string }>();
  const { user, loading } = useAuth();
  const [exam, setExam] = useState<ExamMeta | null>(null);
  const [attempts, setAttempts] = useState<FlaggedAttempt[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<ExamMeta>(`/exams/${params.id}`, { auth: false }).then(setExam).catch(() => setExam(null));
    apiFetch<FlaggedAttempt[]>(`/exams/${params.id}/attempts/flagged`)
      .then(setAttempts)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't load flagged attempts."));
  }, [user, params.id]);

  if (loading) return <div className="mx-auto max-w-4xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user || !user.roles.some((r) => ["INSTRUCTOR", "ADMIN", "SUPER_ADMIN"].includes(r))) {
    return <div className="mx-auto max-w-md px-6 py-24 text-center text-fg-muted">Instructor access required.</div>;
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <Link href="/instructor/courses" className="text-sm text-fg-muted hover:text-fg">&larr; Back to your courses</Link>
      <h1 className="mt-2 text-2xl font-bold text-fg">Integrity review{exam ? ` — ${exam.title}` : ""}</h1>
      <p className="mt-1 text-sm text-fg-muted">
        Every submitted attempt with at least one flagged event — tab switches, fullscreen exits, copy/paste, or late
        submissions. These are informational only; nothing here has auto-failed or auto-submitted a student.
      </p>

      {error && <p className="mt-4 text-sm text-red-700 dark:text-red-400">{error}</p>}

      {attempts !== null && attempts.length === 0 && !error && (
        <div className="card mt-8 text-center text-sm text-fg-muted">No flagged attempts for this exam.</div>
      )}

      <div className="mt-6 space-y-3">
        {(attempts || []).map((a) => (
          <div key={a.attempt_id} className="card !p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-sm font-medium text-fg">{a.student_name}</p>
                <p className="text-xs text-fg-subtle">
                  {a.status} {a.score_percent != null ? `· ${a.score_percent}%` : ""} · {a.flagged_events.length} flagged event(s)
                </p>
              </div>
              <button
                onClick={() => setExpanded(expanded === a.attempt_id ? null : a.attempt_id)}
                className="text-xs text-brand-600 dark:text-brand-400 hover:underline"
              >
                {expanded === a.attempt_id ? "Hide details" : "Show details"}
              </button>
            </div>
            {expanded === a.attempt_id && (
              <ul className="mt-3 space-y-1 border-t border-ink-800 pt-3">
                {a.flagged_events.map((e, i) => (
                  <li key={i} className="flex items-center justify-between text-xs text-fg-muted">
                    <span>{EVENT_LABELS[e.type] || e.type}</span>
                    <span className="text-fg-subtle">{new Date(e.at).toLocaleString()}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
