"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatRelative } from "@/lib/format";

interface Reply { id: string; author_id: string | null; author_name: string; body: string; is_instructor_answer: boolean; created_at: string }
interface ThreadDetail {
  id: string; course_id: string; author_id: string | null; author_name: string; title: string; body: string;
  is_resolved: boolean; upvote_count: number; has_voted: boolean; created_at: string; replies: Reply[];
}

export default function ThreadDetailPage() {
  const params = useParams<{ threadId: string }>();
  const { user } = useAuth();
  const toast = useToast();
  const [thread, setThread] = useState<ThreadDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [replyBody, setReplyBody] = useState("");
  const [posting, setPosting] = useState(false);
  const [voting, setVoting] = useState(false);

  const load = () => {
    apiFetch<ThreadDetail>(`/discussions/${params.threadId}`, { auth: !!user })
      .then(setThread)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't load this discussion."));
  };

  useEffect(load, [params.threadId, user]);

  const reply = async () => {
    if (!replyBody.trim()) return;
    setPosting(true);
    try {
      await apiFetch(`/discussions/${params.threadId}/replies`, { method: "POST", body: JSON.stringify({ body: replyBody }) });
      setReplyBody("");
      load();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't post your reply.", "error");
    } finally {
      setPosting(false);
    }
  };

  const upvote = async () => {
    setVoting(true);
    try {
      const updated = await apiFetch<ThreadDetail>(`/discussions/${params.threadId}/upvote`, { method: "POST" });
      setThread((prev) => (prev ? { ...prev, upvote_count: updated.upvote_count, has_voted: updated.has_voted } : prev));
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't vote.", "error");
    } finally {
      setVoting(false);
    }
  };

  const resolve = async () => {
    try {
      await apiFetch(`/discussions/${params.threadId}/resolve`, { method: "POST" });
      load();
      toast.show("Marked resolved.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Only the course instructor or an admin can resolve this.", "error");
    }
  };

  if (error) {
    return (
      <div className="mx-auto max-w-lg px-6 py-24 text-center">
        <p className="text-red-400">{error}</p>
        <Link href="/courses" className="btn-secondary mt-6 inline-flex">Back to courses</Link>
      </div>
    );
  }
  if (!thread) return <div className="mx-auto max-w-2xl px-6 py-16 text-fg-muted">Loading…</div>;

  const canResolve = user && (user.roles.some((r) => ["INSTRUCTOR", "ADMIN", "SUPER_ADMIN"].includes(r)));

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <div className="card">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-fg">{thread.title}</h1>
            <p className="mt-1 text-xs text-fg-subtle">
              {thread.author_name} · {formatRelative(thread.created_at)}
              {thread.is_resolved && <span className="ml-2 rounded-full bg-emerald-500/15 px-2 py-0.5 text-emerald-300">Resolved</span>}
            </p>
          </div>
          <button
            onClick={upvote}
            disabled={!user || voting}
            className={`shrink-0 rounded-lg border px-3 py-1.5 text-sm ${thread.has_voted ? "border-brand-500 bg-brand-500/10 text-brand-400" : "border-ink-700 text-fg-muted hover:border-ink-600"}`}
          >
            ▲ {thread.upvote_count}
          </button>
        </div>
        <p className="mt-4 whitespace-pre-wrap text-sm text-fg-muted">{thread.body}</p>
        {canResolve && !thread.is_resolved && (
          <button onClick={resolve} className="btn-secondary mt-4 !px-3 !py-1.5 text-xs">Mark resolved</button>
        )}
      </div>

      <div className="mt-6 space-y-3">
        {thread.replies.map((r) => (
          <div key={r.id} className={`card !p-4 ${r.is_instructor_answer ? "border-brand-500/40" : ""}`}>
            <p className="text-sm text-fg-muted">{r.body}</p>
            <p className="mt-2 text-xs text-fg-subtle">
              {r.author_name} {r.is_instructor_answer && <span className="text-brand-400">· Instructor</span>} · {formatRelative(r.created_at)}
            </p>
          </div>
        ))}
      </div>

      {user ? (
        <div className="card mt-6 space-y-3">
          <textarea className="input min-h-20" placeholder="Write a reply…" value={replyBody} onChange={(e) => setReplyBody(e.target.value)} />
          <button onClick={reply} disabled={posting || !replyBody.trim()} className="btn-primary">
            {posting ? "Posting…" : "Reply"}
          </button>
        </div>
      ) : (
        <p className="mt-6 text-center text-sm text-fg-subtle">Sign in to reply.</p>
      )}
    </div>
  );
}
