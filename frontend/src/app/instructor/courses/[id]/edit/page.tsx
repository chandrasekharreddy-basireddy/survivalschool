"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface LessonOut { id: string; title: string; content_type: string; order_index: number }
interface SectionOut { id: string; title: string; order_index: number; lessons: LessonOut[] }
interface CourseDetail {
  id: string; title: string; slug: string; description: string; is_published: boolean;
  difficulty: string; estimated_hours: number;
  skills: string[]; specialization: string | null; sections: SectionOut[];
}
interface QuizSummary { id: string; title: string; is_published: boolean }
interface ExamSummary { id: string; title: string; is_published: boolean }
interface ImportRow { row_number: number; prompt: string; question_type: string; error: string | null }
interface ImportPreview { total_rows: number; valid_rows: number; error_rows: number; rows: ImportRow[]; committed: boolean; inserted_count: number }

export default function EditCoursePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { user, loading } = useAuth();
  const toast = useToast();

  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [quizzes, setQuizzes] = useState<QuizSummary[]>([]);
  const [exams, setExams] = useState<ExamSummary[]>([]);
  const [newSectionTitle, setNewSectionTitle] = useState("");
  const [lessonDrafts, setLessonDrafts] = useState<Record<string, string>>({});
  const [editForm, setEditForm] = useState({ title: "", description: "", difficulty: "beginner", estimated_hours: 1, specialization: "" });
  const [savingCourse, setSavingCourse] = useState(false);
  const [deletingCourse, setDeletingCourse] = useState(false);

  const load = () => {
    apiFetch<CourseDetail>(`/courses/${params.id}`, { auth: false }).then(setCourse).catch(() => setCourse(null));
    apiFetch<QuizSummary[]>(`/courses/${params.id}/quizzes?published_only=false`).then(setQuizzes).catch(() => {});
    apiFetch<ExamSummary[]>(`/courses/${params.id}/exams?published_only=false`).then(setExams).catch(() => {});
  };

  useEffect(() => {
    if (user) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, params.id]);

  useEffect(() => {
    if (course) {
      setEditForm({
        title: course.title, description: course.description, difficulty: course.difficulty,
        estimated_hours: course.estimated_hours, specialization: course.specialization || "",
      });
    }
    // Only re-seed the form when the course identity changes (first load) —
    // not on every background refresh() call from addSection/addLesson,
    // which would otherwise clobber in-progress edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [course?.id]);

  const saveCourseDetails = async () => {
    setSavingCourse(true);
    try {
      const updated = await apiFetch<CourseDetail>(`/courses/${params.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: editForm.title, description: editForm.description, difficulty: editForm.difficulty,
          estimated_hours: editForm.estimated_hours, specialization: editForm.specialization || null,
        }),
      });
      setCourse((prev) => (prev ? { ...prev, ...updated } : prev));
      toast.show("Course details saved.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't save course details.", "error");
    } finally {
      setSavingCourse(false);
    }
  };

  const deleteCourse = async () => {
    if (!window.confirm("Delete this course? Students will lose access and this can't be undone.")) return;
    setDeletingCourse(true);
    try {
      await apiFetch(`/courses/${params.id}`, { method: "DELETE" });
      toast.show("Course deleted.", "success");
      router.push("/instructor/courses");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't delete this course.", "error");
      setDeletingCourse(false);
    }
  };

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

  const canDeleteCourse = user.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r));

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
          <h2 className="font-semibold text-fg">Course details</h2>
          {canDeleteCourse && (
            <button onClick={deleteCourse} disabled={deletingCourse} className="text-xs text-red-400 hover:underline">
              {deletingCourse ? "Deleting…" : "Delete course"}
            </button>
          )}
        </div>
        <div className="mt-4 space-y-4">
          <div>
            <label className="label">Title</label>
            <input className="input" value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} />
          </div>
          <div>
            <label className="label">Description</label>
            <textarea className="input min-h-24" value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label">Difficulty</label>
              <select className="input" value={editForm.difficulty} onChange={(e) => setEditForm({ ...editForm, difficulty: e.target.value })}>
                <option value="beginner">Beginner</option>
                <option value="intermediate">Intermediate</option>
                <option value="advanced">Advanced</option>
              </select>
            </div>
            <div>
              <label className="label">Estimated hours</label>
              <input
                type="number" min={1} className="input" value={editForm.estimated_hours}
                onChange={(e) => setEditForm({ ...editForm, estimated_hours: Number(e.target.value) || 1 })}
              />
            </div>
          </div>
          <div>
            <label className="label">Specialization (optional)</label>
            <input className="input" value={editForm.specialization} onChange={(e) => setEditForm({ ...editForm, specialization: e.target.value })} />
          </div>
          <button onClick={saveCourseDetails} disabled={savingCourse || !editForm.title.trim()} className="btn-primary">
            {savingCourse ? "Saving…" : "Save course details"}
          </button>
        </div>
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

      <BulkImportPanel courseId={course.id} />

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
                <div className="flex items-center gap-3">
                  <Link href={`/instructor/exams/${e.id}/flagged`} className="text-xs text-brand-400 hover:underline">Review flags</Link>
                  <span className={e.is_published ? "text-emerald-400" : "text-amber-400"}>{e.is_published ? "Published" : "Draft"}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Link href="/instructor/courses" className="mt-6 inline-block text-sm text-fg-muted hover:text-fg">&larr; Back to your courses</Link>
    </div>
  );
}

function BulkImportPanel({ courseId }: { courseId: string }) {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [busy, setBusy] = useState(false);

  const runImport = async (dryRun: boolean) => {
    if (!file) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await apiFetch<ImportPreview>(
        `/questions/bulk-import?course_id=${courseId}&dry_run=${dryRun}`,
        { method: "POST", body: form }
      );
      setPreview(res);
      if (dryRun) {
        toast.show(
          res.error_rows === 0
            ? `Looks good — ${res.valid_rows} question(s) ready to import.`
            : `${res.error_rows} row(s) have errors — fix them and re-upload before importing.`,
          res.error_rows === 0 ? "success" : "info"
        );
      } else if (res.committed) {
        toast.show(`Imported ${res.inserted_count} question(s) into the question bank.`, "success");
        setFile(null);
      }
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't import questions.", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card mt-6">
      <h2 className="font-semibold text-fg">Bulk import questions</h2>
      <p className="mt-1 text-sm text-fg-muted">
        Upload a .csv or .xlsx file of questions for this course. Every row is validated first — nothing is written to the
        question bank until you preview it and every row is error-free, then commit.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <input
          type="file"
          accept=".csv,.xlsx"
          onChange={(e) => { setFile(e.target.files?.[0] || null); setPreview(null); }}
          className="text-sm text-fg-muted file:mr-3 file:rounded-lg file:border-0 file:bg-ink-800 file:px-3 file:py-1.5 file:text-sm file:text-fg hover:file:bg-ink-700"
        />
        <button onClick={() => runImport(true)} disabled={!file || busy} className="btn-secondary !px-3 !py-1.5 text-sm">
          {busy ? "Working…" : "Preview"}
        </button>
        <button
          onClick={() => runImport(false)}
          disabled={!file || busy || !preview || preview.error_rows > 0}
          className="btn-primary !px-3 !py-1.5 text-sm"
        >
          Commit import
        </button>
      </div>

      {preview && (
        <div className="mt-4">
          <p className="text-xs text-fg-subtle">
            {preview.total_rows} row(s) &middot; {preview.valid_rows} valid &middot; {preview.error_rows} with errors
            {preview.committed && ` — ${preview.inserted_count} imported`}
          </p>
          <div className="mt-2 max-h-72 overflow-y-auto rounded-lg border border-ink-700">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-ink-900 text-fg-subtle">
                <tr>
                  <th className="px-2 py-1.5 text-left">#</th>
                  <th className="px-2 py-1.5 text-left">Prompt</th>
                  <th className="px-2 py-1.5 text-left">Type</th>
                  <th className="px-2 py-1.5 text-left">Status</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((r) => (
                  <tr key={r.row_number} className="border-t border-ink-800">
                    <td className="px-2 py-1.5 text-fg-subtle">{r.row_number}</td>
                    <td className="max-w-xs truncate px-2 py-1.5 text-fg-muted">{r.prompt || "—"}</td>
                    <td className="px-2 py-1.5 text-fg-muted">{r.question_type || "—"}</td>
                    <td className={`px-2 py-1.5 ${r.error ? "text-red-400" : "text-emerald-400"}`}>{r.error || "OK"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
