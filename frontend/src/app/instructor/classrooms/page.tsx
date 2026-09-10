"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { PageLoader } from "@/components/PageLoader";

interface Subject { id: string; name: string; slug: string }
interface Classroom {
  id: string; name: string; description: string; section: string;
  join_code: string; member_count: number; exam_count: number; is_active: boolean;
}

export default function InstructorClassroomsPage() {
  const { user, loading: authLoading } = useAuth();
  const toast = useToast();

  const [classrooms, setClassrooms] = useState<Classroom[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [section, setSection] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [creating, setCreating] = useState(false);

  const load = () => {
    setFailed(false);
    apiFetch<Classroom[]>("/classrooms/mine").then(setClassrooms).catch(() => setFailed(true));
  };

  useEffect(() => {
    if (!user) return;
    load();
    apiFetch<Subject[]>("/subjects", { auth: false }).then(setSubjects).catch(() => setSubjects([]));
  }, [user]);

  const createClassroom = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    try {
      await apiFetch<Classroom>("/classrooms", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(), description: description.trim(), section: section.trim(),
          subject_id: subjectId || null,
        }),
      });
      setName(""); setDescription(""); setSection(""); setSubjectId(""); setShowCreate(false);
      toast.show("Classroom created.", "success");
      load();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't create the classroom.", "error");
    } finally {
      setCreating(false);
    }
  };

  if (authLoading) return <div className="mx-auto max-w-6xl px-6 py-16"><PageLoader size="md" /></div>;
  if (!user) return <div className="mx-auto max-w-md px-6 py-24 text-center text-fg-muted">Sign in to manage your classrooms.</div>;

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-fg">My classrooms</h1>
          <p className="mt-1 text-sm text-fg-muted">Create a classroom, share the join code with students, and schedule exams.</p>
        </div>
        <button onClick={() => setShowCreate((v) => !v)} className="btn-primary shrink-0">
          {showCreate ? "Cancel" : "+ New classroom"}
        </button>
      </div>

      {showCreate && (
        <form onSubmit={createClassroom} className="card mt-6 space-y-3">
          <input className="input" placeholder="Classroom name" required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
          <div className="grid gap-3 sm:grid-cols-2">
            <select className="input" value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
              <option value="">Subject (optional)…</option>
              {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <input className="input" placeholder="Section (optional)" maxLength={50} value={section} onChange={(e) => setSection(e.target.value)} />
          </div>
          <textarea className="input min-h-20" placeholder="Description (optional)" maxLength={5000} value={description} onChange={(e) => setDescription(e.target.value)} />
          <button type="submit" disabled={creating || !name.trim()} className="btn-primary">
            {creating ? "Creating…" : "Create classroom"}
          </button>
        </form>
      )}

      <div className="mt-8">
        {failed ? (
          <div className="card !p-4 flex items-center justify-between gap-3">
            <p className="text-sm text-fg-muted">Couldn&apos;t load your classrooms.</p>
            <button type="button" onClick={load} className="btn-secondary shrink-0">Retry</button>
          </div>
        ) : classrooms === null ? (
          <PageLoader size="sm" />
        ) : classrooms.length === 0 ? (
          <div className="rounded-lg border border-dashed border-ink-700 p-12 text-center text-sm text-fg-subtle">
            You haven&apos;t created a classroom yet. Click &ldquo;New classroom&rdquo; to get started.
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {classrooms.map((c) => (
              <Link key={c.id} href={`/instructor/classrooms/${c.id}`} className="card transition hover:border-brand-500/50">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-semibold text-fg">{c.name}</h3>
                  {!c.is_active && <span className="shrink-0 rounded-full border border-ink-700 px-2 py-0.5 text-[0.65rem] text-fg-subtle">inactive</span>}
                </div>
                {c.section && <p className="mt-0.5 text-xs text-fg-subtle">Section: {c.section}</p>}
                <p className="mt-2 text-sm text-fg-muted line-clamp-2">{c.description || "No description"}</p>
                <div className="mt-4 flex items-center justify-between text-xs text-fg-subtle">
                  <span>{c.member_count} student{c.member_count !== 1 ? "s" : ""} · {c.exam_count} exam{c.exam_count !== 1 ? "s" : ""}</span>
                  <code className="rounded bg-ink-800 px-1.5 py-0.5 text-brand-400">{c.join_code}</code>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
