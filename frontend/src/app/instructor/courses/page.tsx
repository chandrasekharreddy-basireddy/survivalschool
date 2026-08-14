"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface CourseOut {
  id: string;
  title: string;
  slug: string;
  is_published: boolean;
  instructor_id: string | null;
  created_at: string;
}

export default function InstructorCoursesPage() {
  const { user, loading } = useAuth();
  const toast = useToast();
  const [courses, setCourses] = useState<CourseOut[] | null>(null);

  const load = () => {
    apiFetch<CourseOut[]>("/courses?published_only=false&limit=200")
      .then((all) => setCourses(all.filter((c) => c.instructor_id === user?.id)))
      .catch(() => setCourses([]));
  };

  useEffect(() => {
    if (user) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const togglePublish = async (course: CourseOut) => {
    try {
      await apiFetch(`/courses/${course.id}/${course.is_published ? "unpublish" : "publish"}`, { method: "POST" });
      toast.show(course.is_published ? "Course unpublished." : "Course published.", "success");
      load();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't update the course.", "error");
    }
  };

  if (loading) return <div className="mx-auto max-w-4xl px-6 py-16 text-slate-400">Loading…</div>;
  if (!user || !user.roles.some((r) => ["INSTRUCTOR", "ADMIN", "SUPER_ADMIN"].includes(r))) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-slate-300">This area is for instructors.</p>
        <Link href="/dashboard" className="btn-secondary mt-6 inline-flex">Back to dashboard</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Your courses</h1>
        <Link href="/instructor/courses/create" className="btn-primary">+ New course</Link>
      </div>

      {courses === null ? (
        <p className="mt-8 text-sm text-slate-500">Loading…</p>
      ) : courses.length === 0 ? (
        <div className="mt-8 rounded-lg border border-dashed border-ink-700 p-10 text-center text-sm text-slate-500">
          You haven&apos;t created any courses yet.
        </div>
      ) : (
        <ul className="mt-8 space-y-3">
          {courses.map((c) => (
            <li key={c.id} className="card flex items-center justify-between">
              <div>
                <p className="font-medium text-white">{c.title}</p>
                <p className="text-xs text-slate-500">/{c.slug}</p>
              </div>
              <div className="flex items-center gap-3">
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${c.is_published ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-300"}`}>
                  {c.is_published ? "Published" : "Draft"}
                </span>
                <Link href={`/instructor/courses/${c.id}/edit`} className="btn-secondary !px-3 !py-1.5 text-sm">Manage</Link>
                <button onClick={() => togglePublish(c)} className="btn-secondary !px-3 !py-1.5 text-sm">
                  {c.is_published ? "Unpublish" : "Publish"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
