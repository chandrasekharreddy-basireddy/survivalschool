"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatRelative } from "@/lib/format";

interface Lesson { id: string; title: string; duration_minutes: number; is_completed: boolean }
interface Section { id: string; title: string; lessons: Lesson[] }
interface CourseDetail { id: string; title: string; description: string; sections: Section[] }
interface ThreadSummary { id: string; title: string; author_name: string; is_resolved: boolean; reply_count: number; upvote_count: number; created_at: string }

export default function CourseDetailPage() {
  const params = useParams<{ slug: string }>();
  const { user } = useAuth();
  const toast = useToast();
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [enrolling, setEnrolling] = useState(false);
  const [enrolled, setEnrolled] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [threads, setThreads] = useState<ThreadSummary[] | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newBody, setNewBody] = useState("");
  const [posting, setPosting] = useState(false);

  const load = () => {
    apiFetch<CourseDetail[]>("/courses", { auth: false })
      .then(async (list) => {
        const match = list.find((c: any) => c.slug === params.slug);
        if (!match) return;
        const detail = await apiFetch<CourseDetail>(`/courses/${(match as any).id}`, { auth: false });
        setCourse(detail);
        apiFetch<ThreadSummary[]>(`/courses/${detail.id}/discussions`, { auth: false }).then(setThreads).catch(() => setThreads([]));
      })
      .catch(() => {});
  };

  useEffect(load, [params.slug]);

  const postThread = async () => {
    if (!course || !newTitle.trim() || !newBody.trim()) return;
    setPosting(true);
    try {
      await apiFetch(`/courses/${course.id}/discussions`, {
        method: "POST",
        body: JSON.stringify({ title: newTitle, body: newBody }),
      });
      setNewTitle("");
      setNewBody("");
      toast.show("Discussion started.", "success");
      apiFetch<ThreadSummary[]>(`/courses/${course.id}/discussions`, { auth: false }).then(setThreads).catch(() => {});
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Enroll in this course to start a discussion.", "error");
    } finally {
      setPosting(false);
    }
  };

  const enroll = async () => {
    if (!course) return;
    setEnrolling(true);
    try {
      await apiFetch(`/courses/${course.id}/enroll`, { method: "POST" });
      setEnrolled(true);
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Could not enroll.");
    } finally {
      setEnrolling(false);
    }
  };

  const completeLesson = async (lessonId: string) => {
    try {
      await apiFetch(`/lessons/${lessonId}/complete`, { method: "POST" });
      load();
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Could not mark complete.");
    }
  };

  if (!course) return <div className="mx-auto max-w-4xl px-6 py-16 text-fg-muted">Loading…</div>;

  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <h1 className="text-2xl font-bold text-fg">{course.title}</h1>
      <p className="mt-2 text-fg-muted">{course.description}</p>

      {user ? (
        <button onClick={enroll} disabled={enrolling || enrolled} className="btn-primary mt-6">
          {enrolled ? "Enrolled ✓" : enrolling ? "Enrolling…" : "Enroll in this course"}
        </button>
      ) : (
        <p className="mt-6 text-sm text-fg-subtle">Sign in to enroll and track progress.</p>
      )}
      {message && <p className="mt-3 text-sm text-red-700 dark:text-red-400">{message}</p>}

      <div className="mt-10 space-y-6">
        {course.sections.map((section) => (
          <div key={section.id} className="card">
            <h2 className="font-semibold text-fg">{section.title}</h2>
            <ul className="mt-4 divide-y divide-ink-800">
              {section.lessons.map((lesson) => (
                <li key={lesson.id} className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm text-fg">{lesson.title}</p>
                    <p className="text-xs text-fg-subtle">{lesson.duration_minutes} min</p>
                  </div>
                  {user && (
                    <button
                      onClick={() => completeLesson(lesson.id)}
                      disabled={lesson.is_completed}
                      className="btn-secondary !px-3 !py-1.5 text-xs"
                    >
                      {lesson.is_completed ? "Completed ✓" : "Mark complete"}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="mt-10">
        <h2 className="font-semibold text-fg">Discussion</h2>
        <p className="mt-1 text-sm text-fg-muted">Ask a question or help a classmate — instructor replies are marked.</p>

        {user && (
          <div className="card mt-4 space-y-3">
            <input className="input" placeholder="Title" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
            <textarea className="input min-h-24" placeholder="What's your question?" value={newBody} onChange={(e) => setNewBody(e.target.value)} />
            <button onClick={postThread} disabled={posting || !newTitle.trim() || !newBody.trim()} className="btn-primary">
              {posting ? "Posting…" : "Start a discussion"}
            </button>
          </div>
        )}

        <div className="mt-4 space-y-2">
          {threads === null && <p className="text-sm text-fg-subtle">Loading…</p>}
          {threads !== null && threads.length === 0 && <p className="text-sm text-fg-subtle">No discussions yet — be the first to ask something.</p>}
          {threads?.map((t) => (
            <Link key={t.id} href={`/discussions/${t.id}`} className="card !p-4 flex items-center justify-between gap-4 transition hover:border-brand-500/50">
              <div className="min-w-0">
                <p className="truncate font-medium text-fg">{t.title}</p>
                <p className="text-xs text-fg-subtle">
                  {t.author_name} · {formatRelative(t.created_at)} · {t.reply_count} repl{t.reply_count === 1 ? "y" : "ies"}
                  {t.is_resolved && " · resolved"}
                </p>
              </div>
              <span className="shrink-0 text-xs text-fg-subtle">▲ {t.upvote_count}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
