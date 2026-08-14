"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface LessonOut { id: string; title: string; content_type: string; order_index: number }
interface SectionOut { id: string; title: string; order_index: number; lessons: LessonOut[] }
interface CourseDetail {
  id: string; title: string; slug: string; description: string; is_published: boolean;
  skills: string[]; specialization: string | null; sections: SectionOut[];
}
interface QuizSummary { id: string; title: string; is_published: boolean }
interface ExamSummary { id: string; title: string; is_published: boolean }

export default function EditCoursePage() {
  const params = useParams<{ id: string }>();
  const { user, loading } = useAuth();
  const toast = useToast();

  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [quizzes, setQuizzes] = useState<QuizSummary[]>([]);
  const [exams, setExams] = useState<ExamSummary[]>([]);
  const [newSectionTitle, setNewSectionTitle] = useState("");
  const [lessonDrafts, setLessonDrafts] = useState<Record<string, string>>({});

  const load = () => {
    apiFetch<CourseDetail>(`/courses/${params.id}`, { auth: false }).then(setCourse).catch(() => setCourse(null));
    apiFetch<QuizSummary[]>(`/courses/${params.id}/quizzes?published_only=false`).then(setQuizzes).catch(() => {});
    apiFetch<ExamSummary[]>(`/courses/${params.id}/exams?published_only=false`).then(setExams).catch(() => {});
  };

  useEffect(() => {
    if (user) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, params.id]);

  const addSection = async () => {
    if (!newSectionTitle.trim()) return;
    try {
      await apiFetch(`/courses/${params.id}/sections`, {
        method: "POST",
        body: JSON.stringify({ title: newSectionTitle, order_index: course?.sections.length ?? 0 }),
      });
      setNewSectionTitle("");
      load();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't add the section.", "error");
    }
  };

  const addLesson = async (sectionId: string) => {
    const title = lessonDrafts[sectionId];
    if (!title?.trim()) return;
    try {
      await apiFetch(`/lessons/sections/${sectionId}`, {
        method: "POST",
        body: JSON.stringify({ title, content_type: "article", content_body: "", order_index: 0 }),
      });
      setLessonDrafts((prev) => ({ ...prev, [sectionId]: "" }));
      load();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't add the lesson.", "error");
    }
  };

  if (loading) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user || !user.roles.some((r) => ["INSTRUCTOR", "ADMIN", "SUPER_ADMIN"].includes(r))) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">This area is for instructors.</p>
        <Link href="/dashboard" className="btn-secondary mt-6 inline-flex">Back to dashboard</Link>
      </div>
    );
  }
  if (!course) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-fg">{course.title}</h1>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${course.is_published ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-300"}`}>
          {course.is_published ? "Published" : "Draft"}
        </span>
      </div>

      <div className="card mt-6">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-fg">Content</h2>
        </div>

        {course.sections.length === 0 && <p className="mt-4 text-sm text-fg-subtle">No sections yet.</p>}

        <div className="mt-4 space-y-4">
          {course.sections.map((s) => (
            <div key={s.id} className="rounded-lg border border-ink-700 p-4">
              <p className="font-medium text-fg">{s.title}</p>
              <ul className="mt-2 space-y-1">
                {s.lessons.map((l) => (
                  <li key={l.id} className="text-sm text-fg-muted">&bull; {l.title}</li>
                ))}
              </ul>
              <div className="mt-3 flex gap-2">
                <input
                  className="input !py-1.5 text-sm"
                  placeholder="New lesson title"
                  value={lessonDrafts[s.id] || ""}
                  onChange={(e) => setLessonDrafts((prev) => ({ ...prev, [s.id]: e.target.value }))}
                />
                <button onClick={() => addLesson(s.id)} className="btn-secondary !px-3 !py-1.5 text-sm shrink-0">Add lesson</button>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 flex gap-2 border-t border-ink-800 pt-4">
          <input className="input" placeholder="New section title" value={newSectionTitle} onChange={(e) => setNewSectionTitle(e.target.value)} />
          <button onClick={addSection} className="btn-primary shrink-0">Add section</button>
        </div>
      </div>

      <div className="card mt-6">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-fg">Quizzes</h2>
          <Link href={`/instructor/quizzes/create?course_id=${course.id}`} className="text-sm text-brand-400 hover:underline">+ New quiz</Link>
        </div>
        {quizzes.length === 0 ? (
          <p className="mt-3 text-sm text-fg-subtle">No quizzes yet.</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {quizzes.map((q) => (
              <li key={q.id} className="flex items-center justify-between text-sm">
                <span className="text-fg-muted">{q.title}</span>
                <span className={q.is_published ? "text-emerald-400" : "text-amber-400"}>{q.is_published ? "Published" : "Draft"}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card mt-6">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-fg">Exams</h2>
          <Link href={`/instructor/exams/create?course_id=${course.id}`} className="text-sm text-brand-400 hover:underline">+ New exam</Link>
        </div>
        {exams.length === 0 ? (
          <p className="mt-3 text-sm text-fg-subtle">No exams yet.</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {exams.map((e) => (
              <li key={e.id} className="flex items-center justify-between text-sm">
                <span className="text-fg-muted">{e.title}</span>
                <span className={e.is_published ? "text-emerald-400" : "text-amber-400"}>{e.is_published ? "Published" : "Draft"}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Link href="/instructor/courses" className="mt-6 inline-block text-sm text-fg-muted hover:text-fg">&larr; Back to your courses</Link>
    </div>
  );
}
