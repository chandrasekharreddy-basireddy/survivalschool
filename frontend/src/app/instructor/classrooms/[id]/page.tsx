"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { PageLoader } from "@/components/PageLoader";

interface Classroom {
  id: string; name: string; description: string; section: string;
  join_code: string; member_count: number; exam_count: number; is_active: boolean;
}
interface Exam {
  id: string; title: string; description: string; question_count: number;
  duration_seconds: number; starts_at: string | null; ends_at: string | null; status: string;
}
interface Member { id: string; student_id: string; student_name: string; student_email: string; joined_at: string }

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

export default function InstructorClassroomManagePage() {
  const { id } = useParams<{ id: string }>();
  const toast = useToast();

  const [classroom, setClassroom] = useState<Classroom | null>(null);
  const [exams, setExams] = useState<Exam[] | null>(null);
  const [members, setMembers] = useState<Member[] | null>(null);
  const [tab, setTab] = useState<"exams" | "members" | "settings">("exams");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => {
    apiFetch<Classroom>(`/classrooms/${id}`).then(setClassroom).catch((e) => setError(e?.message || "Not found"));
    apiFetch<Exam[]>(`/classrooms/${id}/exams`).then(setExams).catch(() => setExams([]));
    apiFetch<Member[]>(`/classrooms/${id}/members`).then(setMembers).catch(() => setMembers([]));
  }, [id]);

  useEffect(() => { if (id) load(); }, [id, load]);

  const copyCode = () => {
    if (!classroom) return;
    navigator.clipboard?.writeText(classroom.join_code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  const removeMember = async (studentId: string) => {
    if (!confirm("Remove this student from the classroom?")) return;
    try {
      await apiFetch(`/classrooms/${id}/members/${studentId}`, { method: "DELETE" });
      setMembers((prev) => prev?.filter((m) => m.student_id !== studentId) ?? null);
      toast.show("Student removed.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't remove student.", "error");
    }
  };

  const publishExam = async (examId: string) => {
    try {
      await apiFetch(`/classrooms/${id}/exams/${examId}/publish`, { method: "POST" });
      toast.show("Exam published.", "success");
      load();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't publish the exam.", "error");
    }
  };

  const toggleActive = async () => {
    if (!classroom) return;
    try {
      const updated = await apiFetch<Classroom>(`/classrooms/${id}`, {
        method: "PUT",
        body: JSON.stringify({ is_active: !classroom.is_active }),
      });
      setClassroom(updated);
      toast.show(updated.is_active ? "Classroom reactivated." : "Classroom deactivated.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't update the classroom.", "error");
    }
  };

  if (error) return <div className="mx-auto max-w-4xl px-6 py-16 text-center text-fg-muted">{error}</div>;
  if (!classroom) return <div className="mx-auto max-w-4xl px-6 py-16"><PageLoader size="md" /></div>;

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <Link href="/instructor/classrooms" className="text-sm text-brand-600 dark:text-brand-400 hover:underline">&larr; My classrooms</Link>
      <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-fg">{classroom.name}</h1>
          {classroom.section && <p className="mt-0.5 text-sm text-fg-subtle">Section: {classroom.section}</p>}
          <p className="mt-1 text-sm text-fg-muted">{classroom.description}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button onClick={copyCode} className="btn-secondary !px-3 !py-1.5 text-sm">
            {copied ? "Copied!" : `Code: ${classroom.join_code}`}
          </button>
          <Link href={`/instructor/classrooms/${id}/exams/new`} className="btn-primary !px-3 !py-1.5 text-sm">+ New exam</Link>
        </div>
      </div>

      <div className="mt-8 flex gap-1 border-b border-ink-700">
        {(["exams", "members", "settings"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-sm font-medium capitalize transition ${tab === t ? "border-b-2 border-brand-500 text-fg" : "text-fg-muted hover:text-fg"}`}>
            {t === "exams" ? `Exams (${exams?.length ?? 0})` : t === "members" ? `Students (${members?.length ?? 0})` : "Settings"}
          </button>
        ))}
      </div>

      {tab === "exams" && (
        <div className="mt-6 space-y-3">
          {exams === null ? <PageLoader size="sm" /> : exams.length === 0 ? (
            <div className="rounded-lg border border-dashed border-ink-700 p-12 text-center text-sm text-fg-subtle">
              No exams yet. Create one to get started.
            </div>
          ) : exams.map((e) => (
            <div key={e.id} className="card !p-4 flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-medium text-fg">{e.title}</p>
                <p className="text-xs text-fg-subtle">
                  {e.question_count} question{e.question_count !== 1 ? "s" : ""} · {Math.round(e.duration_seconds / 60)} min
                  {e.starts_at && <> · Join {formatDate(e.starts_at)} – {formatDate(e.ends_at)}</>}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${STATUS_STYLE[e.status] || ""}`}>{e.status}</span>
                {(e.status === "draft" || e.status === "scheduled") && (
                  <Link href={`/instructor/classrooms/${id}/exams/new?examId=${e.id}`} className="btn-secondary !px-2.5 !py-1 text-xs">Edit</Link>
                )}
                {e.status === "scheduled" && (
                  <button onClick={() => publishExam(e.id)} className="btn-secondary !px-2.5 !py-1 text-xs">Open now</button>
                )}
                {(e.status === "open" || e.status === "closed") && (
                  <Link href={`/instructor/classrooms/${id}/exams/${e.id}/results`} className="btn-secondary !px-2.5 !py-1 text-xs">Results</Link>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "members" && (
        <div className="mt-6">
          {members === null ? <PageLoader size="sm" /> : members.length === 0 ? (
            <div className="rounded-lg border border-dashed border-ink-700 p-12 text-center text-sm text-fg-subtle">
              No students yet. Share the join code <code className="rounded bg-ink-800 px-1.5 py-0.5 text-brand-400">{classroom.join_code}</code> with your class.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-ink-700 text-left text-xs uppercase text-fg-subtle">
                    <th className="pb-2 pr-4">Name</th>
                    <th className="pb-2 pr-4">Email</th>
                    <th className="pb-2 pr-4">Joined</th>
                    <th className="pb-2" />
                  </tr>
                </thead>
                <tbody>
                  {members.map((m) => (
                    <tr key={m.id} className="border-b border-ink-800">
                      <td className="py-2.5 pr-4 text-fg">{m.student_name}</td>
                      <td className="py-2.5 pr-4 text-fg-muted">{m.student_email}</td>
                      <td className="py-2.5 pr-4 text-fg-subtle">{formatDate(m.joined_at)}</td>
                      <td className="py-2.5 text-right">
                        <button onClick={() => removeMember(m.student_id)} className="text-xs text-fg-subtle hover:text-red-500">Remove</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "settings" && (
        <div className="card mt-6 max-w-md">
          <h3 className="font-semibold text-fg">Classroom status</h3>
          <p className="mt-1 text-sm text-fg-muted">
            {classroom.is_active
              ? "Active — students can join and see exams."
              : "Inactive — hidden from students; existing exams stay visible to you only."}
          </p>
          <button onClick={toggleActive} className="btn-secondary mt-4">
            {classroom.is_active ? "Deactivate classroom" : "Reactivate classroom"}
          </button>
        </div>
      )}
    </div>
  );
}
