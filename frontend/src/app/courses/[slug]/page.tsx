"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";

interface Lesson { id: string; title: string; duration_minutes: number; is_completed: boolean }
interface Section { id: string; title: string; lessons: Lesson[] }
interface CourseDetail { id: string; title: string; description: string; sections: Section[] }

export default function CourseDetailPage() {
  const params = useParams<{ slug: string }>();
  const { user } = useAuth();
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [enrolling, setEnrolling] = useState(false);
  const [enrolled, setEnrolled] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = () => {
    apiFetch<CourseDetail[]>("/courses", { auth: false })
      .then(async (list) => {
        const match = list.find((c: any) => c.slug === params.slug);
        if (!match) return;
        const detail = await apiFetch<CourseDetail>(`/courses/${(match as any).id}`, { auth: false });
        setCourse(detail);
      })
      .catch(() => {});
  };

  useEffect(load, [params.slug]);

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

  if (!course) return <div className="mx-auto max-w-4xl px-6 py-16 text-slate-400">Loading…</div>;

  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <h1 className="text-2xl font-bold text-white">{course.title}</h1>
      <p className="mt-2 text-slate-400">{course.description}</p>

      {user ? (
        <button onClick={enroll} disabled={enrolling || enrolled} className="btn-primary mt-6">
          {enrolled ? "Enrolled ✓" : enrolling ? "Enrolling…" : "Enroll in this course"}
        </button>
      ) : (
        <p className="mt-6 text-sm text-slate-500">Sign in to enroll and track progress.</p>
      )}
      {message && <p className="mt-3 text-sm text-red-400">{message}</p>}

      <div className="mt-10 space-y-6">
        {course.sections.map((section) => (
          <div key={section.id} className="card">
            <h2 className="font-semibold text-white">{section.title}</h2>
            <ul className="mt-4 divide-y divide-ink-800">
              {section.lessons.map((lesson) => (
                <li key={lesson.id} className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm text-slate-200">{lesson.title}</p>
                    <p className="text-xs text-slate-500">{lesson.duration_minutes} min</p>
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
    </div>
  );
}
