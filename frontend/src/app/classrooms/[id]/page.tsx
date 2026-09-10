"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";
import { PageLoader } from "@/components/PageLoader";
import { isInstructor } from "@/lib/roles";

interface Classroom {
  id: string; name: string; description: string; section: string;
  join_code: string; lecturer_id: string; lecturer_name: string;
  member_count: number; exam_count: number;
}
interface Exam {
  id: string; classroom_id: string; title: string; description: string;
  question_count: number; duration_seconds: number;
  starts_at: string | null; ends_at: string | null; status: string;
}
interface Member {
  id: string; student_id: string; student_name: string; student_email: string; joined_at: string;
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

const STATUS_STYLE: Record<string, string> = {
  draft: "text-fg-subtle border-ink-700",
  scheduled: "text-brand-600 dark:text-brand-400 border-brand-500/40",
  open: "text-emerald-700 dark:text-emerald-400 border-emerald-500/40",
  closed: "text-fg-subtle border-ink-700",
};

export default function ClassroomDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [classroom, setClassroom] = useState<Classroom | null>(null);
  const [exams, setExams] = useState<Exam[] | null>(null);
  const [members, setMembers] = useState<Member[] | null>(null);
  const [tab, setTab] = useState<"exams" | "members">("exams");
  const [error, setError] = useState("");

  const isLecturer = user && classroom && (classroom.lecturer_id === user.id || isInstructor(user));

  useEffect(() => {
    if (!id) return;
    apiFetch<Classroom>(`/classrooms/${id}`).then(setClassroom).catch(e => setError(e?.message || "Not found"));
    apiFetch<Exam[]>(`/classrooms/${id}/exams`).then(setExams).catch(() => setExams([]));
    apiFetch<Member[]>(`/classrooms/${id}/members`).then(setMembers).catch(() => setMembers([]));
  }, [id]);

  if (error) return <div className="mx-auto max-w-4xl px-6 py-16 text-center text-fg-muted">{error}</div>;
  if (!classroom) return <div className="mx-auto max-w-4xl px-6 py-16"><PageLoader size="md" /></div>;

  const upcoming = exams?.filter(e => e.status === "scheduled" || e.status === "open") ?? [];
  const completed = exams?.filter(e => e.status === "closed") ?? [];

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <Link href="/classrooms" className="text-sm text-brand-600 dark:text-brand-400 hover:underline">&larr; All classrooms</Link>
      <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-fg">{classroom.name}</h1>
          {classroom.section && <p className="mt-0.5 text-sm text-fg-subtle">Section: {classroom.section}</p>}
          <p className="mt-1 text-sm text-fg-muted">{classroom.description}</p>
          <p className="mt-2 text-xs text-fg-subtle">
            Instructor: {classroom.lecturer_name} · {classroom.member_count} students · Join code: <code className="rounded bg-ink-800 px-1.5 py-0.5 text-brand-400">{classroom.join_code}</code>
          </p>
        </div>
        {isLecturer && (
          <Link href={`/instructor/classrooms/${id}`} className="btn-secondary shrink-0">Manage</Link>
        )}
      </div>

      <div className="mt-8 flex gap-1 border-b border-ink-700">
        {(["exams", "members"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-sm font-medium capitalize transition ${tab === t ? "border-b-2 border-brand-500 text-fg" : "text-fg-muted hover:text-fg"}`}>
            {t === "exams" ? `Exams (${exams?.length ?? 0})` : `Members (${members?.length ?? 0})`}
          </button>
        ))}
      </div>

      {tab === "exams" && (
        <div className="mt-6 space-y-6">
          {upcoming.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wider text-fg-subtle">Upcoming / Open</h3>
              <div className="mt-3 space-y-3">
                {upcoming.map(e => (
                  <Link key={e.id} href={`/classrooms/${id}/exam/${e.id}`} className="card !p-4 flex items-center justify-between gap-4 transition hover:border-brand-500/50">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-fg">{e.title}</p>
                      <p className="text-xs text-fg-subtle">{e.question_count} questions · {Math.round(e.duration_seconds / 60)} min · Join {formatDate(e.starts_at)} – {formatDate(e.ends_at)}</p>
                    </div>
                    <span className={`shrink-0 rounded-full border px-2.5 py-1 text-xs font-medium ${STATUS_STYLE[e.status] || ""}`}>
                      {e.status}
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          )}
          {completed.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wider text-fg-subtle">Completed</h3>
              <div className="mt-3 space-y-3">
                {completed.map(e => (
                  <div key={e.id} className="card !p-4 flex items-center justify-between gap-4">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-fg">{e.title}</p>
                      <p className="text-xs text-fg-subtle">{e.question_count} questions · Ended {formatDate(e.ends_at)}</p>
                    </div>
                    <span className="shrink-0 rounded-full border border-ink-700 px-2.5 py-1 text-xs text-fg-subtle">closed</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {exams !== null && exams.length === 0 && (
            <p className="text-sm text-fg-subtle">No exams yet.</p>
          )}
        </div>
      )}

      {tab === "members" && (
        <div className="mt-6">
          {members === null ? <PageLoader size="sm" /> : members.length === 0 ? (
            <p className="text-sm text-fg-subtle">No members yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-ink-700 text-left text-xs uppercase text-fg-subtle">
                    <th className="pb-2 pr-4">Name</th>
                    <th className="pb-2 pr-4">Email</th>
                    <th className="pb-2">Joined</th>
                  </tr>
                </thead>
                <tbody>
                  {members.map(m => (
                    <tr key={m.id} className="border-b border-ink-800">
                      <td className="py-2.5 pr-4 text-fg">{m.student_name}</td>
                      <td className="py-2.5 pr-4 text-fg-muted">{m.student_email}</td>
                      <td className="py-2.5 text-fg-subtle">{formatDate(m.joined_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
