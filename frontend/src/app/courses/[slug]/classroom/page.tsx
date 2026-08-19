"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatDateTime, formatRelative } from "@/lib/format";

interface CourseSummary { id: string; slug: string; title: string; instructor_name?: string | null }

type Tab = "stream" | "classwork" | "people" | "grades";
const TABS: { key: Tab; label: string }[] = [
  { key: "stream", label: "Stream" },
  { key: "classwork", label: "Classwork" },
  { key: "people", label: "People" },
  { key: "grades", label: "Grades" },
];

export default function ClassroomPage() {
  const params = useParams<{ slug: string }>();
  const { user, loading: authLoading } = useAuth();
  const [course, setCourse] = useState<CourseSummary | null>(null);
  const [isStaff, setIsStaff] = useState(false);
  const [notMember, setNotMember] = useState(false);
  const [tab, setTab] = useState<Tab>("stream");

  useEffect(() => {
    if (!user) return;

    (async () => {
      try {
        // Try the public (published) catalog first — that's what covers
        // every enrolled student. published_only=false only falls back for
        // the rarer case of an instructor opening their own still-unpublished
        // draft — the backend scopes that branch to "your own courses", so it
        // comes back empty for anyone who isn't that course's owner (a
        // student can never find any course through it, published or not).
        const published = await apiFetch<CourseSummary[]>("/courses?published_only=true&limit=200");
        let match = published.find((c) => c.slug === params.slug);
        if (!match) {
          const own = await apiFetch<CourseSummary[]>("/courses?published_only=false");
          match = own.find((c) => c.slug === params.slug);
        }
        if (!match) {
          setNotMember(true);
          return;
        }
        setCourse(match);
        const people = await apiFetch<{ user_id: string; role: string }[]>(`/courses/${match.id}/people`);
        setIsStaff(people.some((p) => p.role === "instructor" && p.user_id === user.id) || user.roles.includes("ADMIN") || user.roles.includes("SUPER_ADMIN"));
      } catch (err) {
        // A genuine "you can't see this" (401/403) means not a member. Any
        // other failure — including a duplicate in-flight request that lost a
        // race with itself (e.g. React StrictMode's double effect invocation
        // in dev) — must not be treated as a permanent verdict; the other,
        // successful invocation already set the right state.
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          setNotMember(true);
        }
      }
    })();
  }, [user, params.slug]);

  if (authLoading) return <div className="mx-auto max-w-4xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to view this class.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }
  if (notMember) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">You&apos;re not a member of this class.</p>
        <Link href="/courses" className="btn-secondary mt-6 inline-flex">Browse courses</Link>
      </div>
    );
  }
  if (!course) return <div className="mx-auto max-w-4xl px-6 py-16 text-fg-muted">Loading…</div>;

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-fg">{course.title}</h1>
          <p className="mt-1 text-sm text-fg-muted">Classroom</p>
        </div>
        <Link href={`/courses/${course.slug}`} className="text-sm text-brand-600 dark:text-brand-400 hover:underline">Course page &rarr;</Link>
      </div>

      <div className="mt-6 flex gap-1 border-b border-ink-800">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-t-lg px-3 py-2 text-sm font-medium transition-colors ${
              tab === t.key ? "border-b-2 border-brand-600 text-fg dark:border-brand-400" : "text-fg-muted hover:text-fg"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === "stream" && <StreamTab courseId={course.id} isStaff={isStaff} />}
        {tab === "classwork" && <ClassworkTab courseId={course.id} isStaff={isStaff} />}
        {tab === "people" && <PeopleTab courseId={course.id} />}
        {tab === "grades" && <GradesTab courseId={course.id} isStaff={isStaff} />}
      </div>
    </div>
  );
}

// ---- Stream ----

interface AnnouncementOut {
  id: string; author_name: string; body: string; is_pinned: boolean; comment_count: number; created_at: string;
}
interface CommentOut { id: string; author_name: string; body: string; created_at: string }

function StreamTab({ courseId, isStaff }: { courseId: string; isStaff: boolean }) {
  const toast = useToast();
  const [items, setItems] = useState<AnnouncementOut[] | null>(null);
  const [draft, setDraft] = useState("");
  const [posting, setPosting] = useState(false);
  const [openComments, setOpenComments] = useState<string | null>(null);
  const [comments, setComments] = useState<Record<string, CommentOut[]>>({});
  const [commentDraft, setCommentDraft] = useState("");

  const load = () => apiFetch<AnnouncementOut[]>(`/courses/${courseId}/stream`).then(setItems).catch(() => setItems([]));
  useEffect(() => { load(); }, [courseId]); // eslint-disable-line react-hooks/exhaustive-deps

  const post = async () => {
    if (!draft.trim()) return;
    setPosting(true);
    try {
      await apiFetch(`/courses/${courseId}/stream`, { method: "POST", body: JSON.stringify({ body: draft, is_pinned: false }) });
      setDraft("");
      load();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't post.", "error");
    } finally {
      setPosting(false);
    }
  };

  const toggleComments = async (id: string) => {
    if (openComments === id) { setOpenComments(null); return; }
    setOpenComments(id);
    if (!comments[id]) {
      const c = await apiFetch<CommentOut[]>(`/courses/${courseId}/stream/${id}/comments`).catch(() => []);
      setComments((prev) => ({ ...prev, [id]: c }));
    }
  };

  const postComment = async (id: string) => {
    if (!commentDraft.trim()) return;
    try {
      await apiFetch(`/courses/${courseId}/stream/${id}/comments`, { method: "POST", body: JSON.stringify({ body: commentDraft }) });
      setCommentDraft("");
      const c = await apiFetch<CommentOut[]>(`/courses/${courseId}/stream/${id}/comments`).catch(() => []);
      setComments((prev) => ({ ...prev, [id]: c }));
      load();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't comment.", "error");
    }
  };

  return (
    <div className="space-y-4">
      {isStaff && (
        <div className="card !p-4">
          <textarea className="input min-h-[80px]" placeholder="Share something with your class…" value={draft} onChange={(e) => setDraft(e.target.value)} />
          <button onClick={post} disabled={posting || !draft.trim()} className="btn-primary mt-2 !py-1.5 text-sm">
            {posting ? "Posting…" : "Post"}
          </button>
        </div>
      )}
      {items === null && <p className="text-sm text-fg-subtle">Loading…</p>}
      {items !== null && items.length === 0 && <p className="text-sm text-fg-subtle">No announcements yet.</p>}
      {items?.map((a) => (
        <div key={a.id} className="card !p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-fg">{a.author_name}</p>
            <p className="text-xs text-fg-subtle">{formatRelative(a.created_at)}</p>
          </div>
          {a.is_pinned && <span className="mt-1 inline-block rounded bg-brand-500/10 px-1.5 py-0.5 text-[11px] text-brand-600 dark:text-brand-400">Pinned</span>}
          <p className="mt-2 whitespace-pre-wrap text-sm text-fg">{a.body}</p>
          <button onClick={() => toggleComments(a.id)} className="mt-2 text-xs text-fg-muted hover:underline">
            {a.comment_count} comment{a.comment_count === 1 ? "" : "s"}
          </button>
          {openComments === a.id && (
            <div className="mt-3 space-y-2 border-t border-ink-800 pt-3">
              {(comments[a.id] || []).map((c) => (
                <div key={c.id} className="text-xs">
                  <span className="font-medium text-fg">{c.author_name}</span>{" "}
                  <span className="text-fg-subtle">{formatRelative(c.created_at)}</span>
                  <p className="mt-0.5 text-fg-muted">{c.body}</p>
                </div>
              ))}
              <div className="flex gap-2">
                <input className="input !py-1 text-xs" placeholder="Add a comment…" value={commentDraft} onChange={(e) => setCommentDraft(e.target.value)} />
                <button onClick={() => postComment(a.id)} className="btn-secondary !px-2 !py-1 text-xs">Send</button>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ---- Classwork ----

interface AssignmentOut {
  id: string; title: string; instructions: string; due_at: string | null; points_possible: number;
  is_published: boolean; created_at: string; my_status: string | null; my_grade: number | null;
}

function ClassworkTab({ courseId, isStaff }: { courseId: string; isStaff: boolean }) {
  const toast = useToast();
  const [items, setItems] = useState<AssignmentOut[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ title: "", instructions: "", due_at: "", points_possible: 100 });
  const [selected, setSelected] = useState<AssignmentOut | null>(null);

  const load = () => apiFetch<AssignmentOut[]>(`/courses/${courseId}/classwork`).then(setItems).catch(() => setItems([]));
  useEffect(() => { load(); }, [courseId]); // eslint-disable-line react-hooks/exhaustive-deps

  const create = async () => {
    if (!form.title.trim()) return;
    setCreating(true);
    try {
      await apiFetch(`/courses/${courseId}/classwork`, {
        method: "POST",
        body: JSON.stringify({
          title: form.title, instructions: form.instructions, points_possible: form.points_possible,
          due_at: form.due_at ? new Date(form.due_at).toISOString() : null,
        }),
      });
      setForm({ title: "", instructions: "", due_at: "", points_possible: 100 });
      toast.show("Assignment posted.", "success");
      load();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't create assignment.", "error");
    } finally {
      setCreating(false);
    }
  };

  if (selected) {
    return isStaff
      ? <AssignmentGrading courseId={courseId} assignment={selected} onBack={() => setSelected(null)} />
      : <AssignmentSubmit courseId={courseId} assignment={selected} onBack={() => { setSelected(null); load(); }} />;
  }

  return (
    <div className="space-y-4">
      {isStaff && (
        <div className="card !p-4 space-y-2">
          <p className="text-sm font-semibold text-fg">New assignment</p>
          <input className="input" placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <textarea className="input min-h-[70px]" placeholder="Instructions" value={form.instructions} onChange={(e) => setForm({ ...form, instructions: e.target.value })} />
          <div className="flex gap-2">
            <input type="datetime-local" className="input !w-auto" value={form.due_at} onChange={(e) => setForm({ ...form, due_at: e.target.value })} />
            <input type="number" min={0} className="input !w-24" value={form.points_possible} onChange={(e) => setForm({ ...form, points_possible: Number(e.target.value) })} />
          </div>
          <button onClick={create} disabled={creating || !form.title.trim()} className="btn-primary !py-1.5 text-sm">
            {creating ? "Posting…" : "Assign"}
          </button>
        </div>
      )}
      {items === null && <p className="text-sm text-fg-subtle">Loading…</p>}
      {items !== null && items.length === 0 && <p className="text-sm text-fg-subtle">No assignments yet.</p>}
      {items?.map((a) => (
        <button key={a.id} onClick={() => setSelected(a)} className="card !p-4 block w-full text-left transition-colors hover:border-brand-500/50">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-fg">{a.title}</p>
            {!isStaff && (
              <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                a.my_status === "graded" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                : a.my_status === "submitted" ? "bg-brand-500/10 text-brand-600 dark:text-brand-400"
                : "bg-ink-800 text-fg-muted"
              }`}>
                {a.my_status === "graded" ? `Graded ${a.my_grade}/${a.points_possible}` : a.my_status === "submitted" ? "Submitted" : "Assigned"}
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-fg-subtle">
            {a.due_at ? `Due ${formatDateTime(a.due_at)}` : "No due date"} · {a.points_possible} points{!a.is_published && isStaff ? " · Draft" : ""}
          </p>
        </button>
      ))}
    </div>
  );
}

function AssignmentSubmit({ courseId, assignment, onBack }: { courseId: string; assignment: AssignmentOut; onBack: () => void }) {
  const toast = useToast();
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [comments, setComments] = useState<CommentOut[]>([]);
  const [commentDraft, setCommentDraft] = useState("");
  const [submissionId, setSubmissionId] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<{ id: string; content: string; status: string; grade: number | null; feedback: string | null }>(
      `/courses/${courseId}/classwork/${assignment.id}/submissions/me`
    ).then((s) => {
      setContent(s.content);
      setSubmissionId(s.id);
      apiFetch<CommentOut[]>(`/courses/${courseId}/classwork/${assignment.id}/submissions/${s.id}/comments`).then(setComments).catch(() => {});
    }).catch(() => {});
  }, [courseId, assignment.id]);

  const submit = async () => {
    setSubmitting(true);
    try {
      await apiFetch(`/courses/${courseId}/classwork/${assignment.id}/submit`, { method: "POST", body: JSON.stringify({ content }) });
      toast.show("Submitted.", "success");
      onBack();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't submit.", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const postComment = async () => {
    if (!commentDraft.trim() || !submissionId) return;
    await apiFetch(`/courses/${courseId}/classwork/${assignment.id}/submissions/${submissionId}/comments`, { method: "POST", body: JSON.stringify({ body: commentDraft }) });
    setCommentDraft("");
    const c = await apiFetch<CommentOut[]>(`/courses/${courseId}/classwork/${assignment.id}/submissions/${submissionId}/comments`).catch(() => []);
    setComments(c);
  };

  return (
    <div>
      <button onClick={onBack} className="text-sm text-brand-600 dark:text-brand-400 hover:underline">&larr; Back to classwork</button>
      <div className="card mt-3 !p-4">
        <h2 className="font-semibold text-fg">{assignment.title}</h2>
        <p className="mt-1 text-xs text-fg-subtle">
          {assignment.due_at ? `Due ${formatDateTime(assignment.due_at)}` : "No due date"} · {assignment.points_possible} points
        </p>
        <p className="mt-3 whitespace-pre-wrap text-sm text-fg-muted">{assignment.instructions}</p>

        {assignment.my_status === "graded" && (
          <div className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3">
            <p className="text-sm font-semibold text-emerald-700 dark:text-emerald-400">Grade: {assignment.my_grade}/{assignment.points_possible}</p>
          </div>
        )}

        <textarea className="input mt-4 min-h-[120px]" placeholder="Your work…" value={content} onChange={(e) => setContent(e.target.value)} />
        <button onClick={submit} disabled={submitting} className="btn-primary mt-2 !py-1.5 text-sm">
          {submitting ? "Submitting…" : assignment.my_status === "not_submitted" ? "Turn in" : "Resubmit"}
        </button>

        <div className="mt-6 border-t border-ink-800 pt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">Private comments</p>
          <div className="mt-2 space-y-2">
            {comments.map((c) => (
              <div key={c.id} className="text-xs">
                <span className="font-medium text-fg">{c.author_name}</span>{" "}
                <span className="text-fg-subtle">{formatRelative(c.created_at)}</span>
                <p className="mt-0.5 text-fg-muted">{c.body}</p>
              </div>
            ))}
            <div className="flex gap-2">
              <input className="input !py-1 text-xs" placeholder="Ask your instructor a question…" value={commentDraft} onChange={(e) => setCommentDraft(e.target.value)} />
              <button onClick={postComment} className="btn-secondary !px-2 !py-1 text-xs">Send</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

interface SubmissionOut {
  id: string; student_id: string; student_name: string; content: string; status: string;
  submitted_at: string | null; grade: number | null; feedback: string | null;
}

function AssignmentGrading({ courseId, assignment, onBack }: { courseId: string; assignment: AssignmentOut; onBack: () => void }) {
  const toast = useToast();
  const [subs, setSubs] = useState<SubmissionOut[] | null>(null);
  const [grading, setGrading] = useState<Record<string, { grade: string; feedback: string }>>({});
  const [saving, setSaving] = useState<string | null>(null);

  const load = () => apiFetch<SubmissionOut[]>(`/courses/${courseId}/classwork/${assignment.id}/submissions`).then(setSubs).catch(() => setSubs([]));
  useEffect(() => { load(); }, [courseId, assignment.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const saveGrade = async (sub: SubmissionOut) => {
    const draft = grading[sub.id];
    if (!draft || draft.grade === "") return;
    setSaving(sub.id);
    try {
      await apiFetch(`/courses/${courseId}/classwork/${assignment.id}/submissions/${sub.id}/grade`, {
        method: "POST", body: JSON.stringify({ grade: Number(draft.grade), feedback: draft.feedback || null }),
      });
      toast.show("Grade saved.", "success");
      load();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't save grade.", "error");
    } finally {
      setSaving(null);
    }
  };

  return (
    <div>
      <button onClick={onBack} className="text-sm text-brand-600 dark:text-brand-400 hover:underline">&larr; Back to classwork</button>
      <h2 className="mt-3 font-semibold text-fg">{assignment.title} — submissions</h2>
      <div className="mt-3 space-y-3">
        {subs === null && <p className="text-sm text-fg-subtle">Loading…</p>}
        {subs?.map((s) => (
          <div key={s.id} className="card !p-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-fg">{s.student_name}</p>
              <span className="text-xs text-fg-subtle capitalize">{s.status.replace("_", " ")}</span>
            </div>
            {s.content && <p className="mt-2 whitespace-pre-wrap text-sm text-fg-muted">{s.content}</p>}
            {s.status !== "not_submitted" && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <input
                  type="number" min={0} max={assignment.points_possible} className="input !w-20 !py-1 text-xs"
                  placeholder={`/${assignment.points_possible}`}
                  value={grading[s.id]?.grade ?? (s.grade ?? "")}
                  onChange={(e) => setGrading((prev) => ({ ...prev, [s.id]: { grade: e.target.value, feedback: prev[s.id]?.feedback ?? s.feedback ?? "" } }))}
                />
                <input
                  className="input !py-1 text-xs flex-1 min-w-[160px]" placeholder="Feedback (optional)"
                  value={grading[s.id]?.feedback ?? (s.feedback ?? "")}
                  onChange={(e) => setGrading((prev) => ({ ...prev, [s.id]: { grade: prev[s.id]?.grade ?? (s.grade?.toString() ?? ""), feedback: e.target.value } }))}
                />
                <button onClick={() => saveGrade(s)} disabled={saving === s.id} className="btn-primary !px-3 !py-1 text-xs">
                  {saving === s.id ? "Saving…" : "Save grade"}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---- People ----

interface RosterMember { user_id: string; full_name: string; email: string; role: string }

function PeopleTab({ courseId }: { courseId: string }) {
  const [members, setMembers] = useState<RosterMember[] | null>(null);
  useEffect(() => { apiFetch<RosterMember[]>(`/courses/${courseId}/people`).then(setMembers).catch(() => setMembers([])); }, [courseId]);

  if (members === null) return <p className="text-sm text-fg-subtle">Loading…</p>;
  const instructors = members.filter((m) => m.role === "instructor");
  const students = members.filter((m) => m.role === "student");

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">Instructor</p>
        <div className="mt-2 space-y-1">
          {instructors.map((m) => <p key={m.user_id} className="text-sm text-fg">{m.full_name} <span className="text-fg-subtle">· {m.email}</span></p>)}
        </div>
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">Students ({students.length})</p>
        <div className="mt-2 space-y-1">
          {students.map((m) => <p key={m.user_id} className="text-sm text-fg">{m.full_name} <span className="text-fg-subtle">· {m.email}</span></p>)}
          {students.length === 0 && <p className="text-sm text-fg-subtle">No students enrolled yet.</p>}
        </div>
      </div>
    </div>
  );
}

// ---- Grades ----

interface GradebookRow { student_id: string; student_name: string; grades: Record<string, number | null>; total_earned: number; total_possible: number }
interface GradebookOut { assignments: AssignmentOut[]; rows: GradebookRow[] }

function GradesTab({ courseId, isStaff }: { courseId: string; isStaff: boolean }) {
  const [gb, setGb] = useState<GradebookOut | null>(null);
  useEffect(() => { apiFetch<GradebookOut>(`/courses/${courseId}/grades`).then(setGb).catch(() => setGb(null)); }, [courseId]);

  if (gb === null) return <p className="text-sm text-fg-subtle">Loading…</p>;
  if (gb.assignments.length === 0) return <p className="text-sm text-fg-subtle">No graded assignments yet.</p>;

  return (
    <div className="card overflow-x-auto !p-0">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-ink-800 text-left text-xs uppercase tracking-wide text-fg-subtle">
            <th className="px-4 py-3">{isStaff ? "Student" : "Assignment"}</th>
            {isStaff ? gb.assignments.map((a) => <th key={a.id} className="px-4 py-3">{a.title}</th>) : <th className="px-4 py-3">Grade</th>}
            {isStaff && <th className="px-4 py-3">Total</th>}
          </tr>
        </thead>
        <tbody>
          {isStaff
            ? gb.rows.map((r) => (
                <tr key={r.student_id} className="border-b border-ink-800 last:border-0">
                  <td className="px-4 py-3 text-fg">{r.student_name}</td>
                  {gb.assignments.map((a) => (
                    <td key={a.id} className="px-4 py-3 text-fg-muted">
                      {r.grades[a.id] === null || r.grades[a.id] === undefined ? "—" : `${r.grades[a.id]}/${a.points_possible}`}
                    </td>
                  ))}
                  <td className="px-4 py-3 font-medium text-fg">{r.total_earned}/{r.total_possible}</td>
                </tr>
              ))
            : gb.assignments.map((a) => (
                <tr key={a.id} className="border-b border-ink-800 last:border-0">
                  <td className="px-4 py-3 text-fg">{a.title}</td>
                  <td className="px-4 py-3 text-fg-muted">{a.my_grade === null ? "—" : `${a.my_grade}/${a.points_possible}`}</td>
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  );
}
