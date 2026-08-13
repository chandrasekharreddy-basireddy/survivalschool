"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";

interface Course {
  id: string;
  title: string;
  slug: string;
  description: string;
  difficulty: string;
  estimated_hours: number;
}

export default function CoursesPage() {
  const [courses, setCourses] = useState<Course[] | null>(null);

  useEffect(() => {
    apiFetch<Course[]>("/courses", { auth: false }).then(setCourses).catch(() => setCourses([]));
  }, []);

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="text-2xl font-bold text-white">Courses</h1>
      <p className="mt-1 text-slate-400">Every course here ends in a real, graded assessment.</p>

      {courses === null ? (
        <p className="mt-8 text-sm text-slate-500">Loading…</p>
      ) : courses.length === 0 ? (
        <div className="mt-8 rounded-lg border border-dashed border-ink-700 p-10 text-center text-sm text-slate-500">
          No published courses yet. Check back soon.
        </div>
      ) : (
        <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {courses.map((c) => (
            <Link key={c.id} href={`/courses/${c.slug}`} className="card block transition hover:border-brand-500/50">
              <span className="inline-block rounded-full bg-ink-800 px-2.5 py-0.5 text-xs capitalize text-slate-400">{c.difficulty}</span>
              <h3 className="mt-3 font-semibold text-white">{c.title}</h3>
              <p className="mt-2 line-clamp-2 text-sm text-slate-400">{c.description}</p>
              <p className="mt-4 text-xs text-slate-500">{c.estimated_hours}h estimated</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
