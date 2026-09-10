"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { PageLoader } from "@/components/PageLoader";

interface Subject { id: string; name: string }
interface Topic { id: string; name: string }
interface QuestionRow { id: string; prompt: string; question_type: string; points: number }
interface ExamOut {
  id: string; title: string; description: string; question_count: number;
  duration_seconds: number; starts_at: string | null; ends_at: string | null; status: string;
  fullscreen_required: boolean; integrity_monitoring_enabled: boolean;
  max_warnings_before_terminate: number; face_proctoring_required: boolean;
}

function toLocalInputValue(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function InstructorExamEditorPage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-3xl px-6 py-16"><PageLoader size="md" /></div>}>
      <InstructorExamEditorInner />
    </Suspense>
  );
}

function InstructorExamEditorInner() {
  const { id: classroomId } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const examId = searchParams.get("examId");
  const router = useRouter();
  const toast = useToast();

  const [loading, setLoading] = useState(!!examId);
  const [saving, setSaving] = useState(false);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [durationMinutes, setDurationMinutes] = useState(30);
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [fullscreenRequired, setFullscreenRequired] = useState(true);
  const [integrityMonitoring, setIntegrityMonitoring] = useState(true);
  const [maxWarnings, setMaxWarnings] = useState(2);
  const [faceProctoring, setFaceProctoring] = useState(false);
  const [selectedQuestionIds, setSelectedQuestionIds] = useState<string[]>([]);
  const [existingStatus, setExistingStatus] = useState<string>("draft");

  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [subjectId, setSubjectId] = useState("");
  const [topicId, setTopicId] = useState("");
  const [search, setSearch] = useState("");
  const [questions, setQuestions] = useState<QuestionRow[]>([]);
  const [questionsLoading, setQuestionsLoading] = useState(false);

  useEffect(() => {
    apiFetch<Subject[]>("/subjects", { auth: false }).then(setSubjects).catch(() => setSubjects([]));
  }, []);

  useEffect(() => {
    if (!subjectId) { setTopics([]); setTopicId(""); return; }
    apiFetch<Topic[]>(`/subjects/${subjectId}/topics`, { auth: false }).then(setTopics).catch(() => setTopics([]));
  }, [subjectId]);

  useEffect(() => {
    setQuestionsLoading(true);
    const params = new URLSearchParams();
    if (subjectId) params.set("subject_id", subjectId);
    if (topicId) params.set("topic_id", topicId);
    if (search.trim()) params.set("search", search.trim());
    apiFetch<QuestionRow[]>(`/questions?${params.toString()}`)
      .then(setQuestions)
      .catch(() => setQuestions([]))
      .finally(() => setQuestionsLoading(false));
  }, [subjectId, topicId, search]);

  useEffect(() => {
    if (!examId) return;
    apiFetch<ExamOut[]>(`/classrooms/${classroomId}/exams`)
      .then((exams) => {
        const found = exams.find((e) => e.id === examId);
        if (!found) { toast.show("Exam not found.", "error"); router.push(`/instructor/classrooms/${classroomId}`); return; }
        setTitle(found.title);
        setDescription(found.description);
        setDurationMinutes(Math.round(found.duration_seconds / 60));
        setStartsAt(toLocalInputValue(found.starts_at));
        setEndsAt(toLocalInputValue(found.ends_at));
        setFullscreenRequired(found.fullscreen_required);
        setIntegrityMonitoring(found.integrity_monitoring_enabled);
        setMaxWarnings(found.max_warnings_before_terminate);
        setFaceProctoring(found.face_proctoring_required);
        setExistingStatus(found.status);
      })
      .finally(() => setLoading(false));
    // Selected question IDs for an existing exam aren't returned by the list
    // endpoint (only a count) -- editing an existing exam's question set
    // starts from the picker fresh rather than round-tripping IDs the UI
    // has no other use for.
  }, [examId, classroomId, router, toast]);

  const toggleQuestion = (qid: string) => {
    setSelectedQuestionIds((prev) => prev.includes(qid) ? prev.filter((id) => id !== qid) : [...prev, qid]);
  };

  const buildPayload = () => ({
    title: title.trim(),
    description: description.trim(),
    duration_seconds: durationMinutes * 60,
    starts_at: startsAt ? new Date(startsAt).toISOString() : null,
    ends_at: endsAt ? new Date(endsAt).toISOString() : null,
    fullscreen_required: fullscreenRequired,
    integrity_monitoring_enabled: integrityMonitoring,
    max_warnings_before_terminate: maxWarnings,
    face_proctoring_required: faceProctoring,
    ...(selectedQuestionIds.length > 0 ? { question_ids: selectedQuestionIds } : {}),
  });

  const save = async (publish: boolean) => {
    if (!title.trim()) { toast.show("Give the exam a title.", "error"); return; }
    if (publish && selectedQuestionIds.length === 0 && !examId) {
      toast.show("Pick at least one question before publishing.", "error");
      return;
    }
    if (publish && (!startsAt || !endsAt)) {
      toast.show("Set a start and end time before publishing.", "error");
      return;
    }
    setSaving(true);
    try {
      const savedExamId = examId
        ? (await apiFetch<ExamOut>(`/classrooms/${classroomId}/exams/${examId}`, { method: "PUT", body: JSON.stringify(buildPayload()) })).id
        : (await apiFetch<ExamOut>(`/classrooms/${classroomId}/exams`, { method: "POST", body: JSON.stringify(buildPayload()) })).id;
      if (publish) {
        await apiFetch(`/classrooms/${classroomId}/exams/${savedExamId}/publish`, { method: "POST" });
        toast.show("Exam published.", "success");
      } else {
        toast.show("Saved as draft.", "success");
      }
      router.push(`/instructor/classrooms/${classroomId}`);
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't save the exam.", "error");
    } finally {
      setSaving(false);
    }
  };

  const questionCountLabel = useMemo(() => {
    if (examId && selectedQuestionIds.length === 0) return "keeping existing questions";
    return `${selectedQuestionIds.length} selected`;
  }, [examId, selectedQuestionIds.length]);

  const examRunsLabel = useMemo(() => {
    if (!endsAt || !durationMinutes) return "";
    const start = new Date(endsAt);
    if (Number.isNaN(start.getTime())) return "";
    const end = new Date(start.getTime() + durationMinutes * 60_000);
    return `Exam runs ${start.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}–${end.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}.`;
  }, [endsAt, durationMinutes]);

  if (loading) return <div className="mx-auto max-w-3xl px-6 py-16"><PageLoader size="md" /></div>;

  const locked = existingStatus === "open" || existingStatus === "closed";

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <Link href={`/instructor/classrooms/${classroomId}`} className="text-sm text-brand-600 dark:text-brand-400 hover:underline">&larr; Back to classroom</Link>
      <h1 className="mt-4 text-2xl font-bold text-fg">{examId ? "Edit exam" : "New exam"}</h1>

      {locked ? (
        <p className="mt-4 text-sm text-fg-muted">This exam is already {existingStatus} and can no longer be edited.</p>
      ) : (
        <>
          <div className="card mt-6 space-y-3">
            <input className="input" placeholder="Exam title" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
            <textarea className="input min-h-20" placeholder="Description (optional)" maxLength={5000} value={description} onChange={(e) => setDescription(e.target.value)} />
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="text-sm text-fg-muted">
                Duration (minutes)
                <input type="number" min={1} max={1440} className="input mt-1" value={durationMinutes} onChange={(e) => setDurationMinutes(Number(e.target.value))} />
              </label>
              <label className="text-sm text-fg-muted">
                Joining opens
                <input type="datetime-local" className="input mt-1" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} />
              </label>
              <label className="text-sm text-fg-muted">
                Joining closes
                <input type="datetime-local" className="input mt-1" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
              </label>
            </div>
            <p className="text-xs text-fg-subtle">
              Students can join any time in that window. The exam itself starts for everyone the moment joining
              closes, and every student gets the full duration from that instant — nobody who joins right at the
              deadline gets shortchanged.
              {examRunsLabel && <> <span className="text-fg-muted">{examRunsLabel}</span></>}
            </p>
          </div>

          <div className="card mt-4">
            <h3 className="font-semibold text-fg">Exam security</h3>
            <div className="mt-3 space-y-2 text-sm text-fg-muted">
              <label className="flex items-center gap-2">
                <input type="checkbox" className="accent-brand-500" checked={fullscreenRequired} onChange={(e) => setFullscreenRequired(e.target.checked)} />
                Require fullscreen
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" className="accent-brand-500" checked={integrityMonitoring} onChange={(e) => setIntegrityMonitoring(e.target.checked)} />
                Monitor tab switches, copy/paste, and device changes
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" className="accent-brand-500" checked={faceProctoring} onChange={(e) => setFaceProctoring(e.target.checked)} />
                Require face proctoring
              </label>
              <label className="flex items-center gap-2">
                Warnings before termination
                <input type="number" min={1} max={10} className="input !w-16 !py-1" value={maxWarnings} onChange={(e) => setMaxWarnings(Number(e.target.value))} />
              </label>
            </div>
          </div>

          <div className="card mt-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-fg">Questions</h3>
              <span className="text-xs text-fg-subtle">{questionCountLabel}</span>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              <select className="input" value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
                <option value="">All subjects</option>
                {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
              <select className="input" value={topicId} onChange={(e) => setTopicId(e.target.value)} disabled={!subjectId}>
                <option value="">All topics</option>
                {topics.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
              <input className="input" placeholder="Search prompt…" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <div className="mt-3 max-h-80 space-y-1 overflow-y-auto rounded-lg border border-ink-800 p-2">
              {questionsLoading ? <PageLoader size="sm" /> : questions.length === 0 ? (
                <p className="p-3 text-center text-sm text-fg-subtle">No questions match. Add some from the Question bank first.</p>
              ) : questions.map((q) => (
                <label key={q.id} className="flex items-start gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-ink-800/60">
                  <input type="checkbox" className="mt-1 accent-brand-500" checked={selectedQuestionIds.includes(q.id)} onChange={() => toggleQuestion(q.id)} />
                  <span className="flex-1 text-fg-muted">{q.prompt}</span>
                  <span className="shrink-0 text-xs text-fg-subtle">{q.points} pt</span>
                </label>
              ))}
            </div>
          </div>

          <div className="mt-6 flex gap-3">
            <button onClick={() => save(false)} disabled={saving} className="btn-secondary">
              {saving ? "Saving…" : "Save as draft"}
            </button>
            <button onClick={() => save(true)} disabled={saving} className="btn-primary">
              {saving ? "Publishing…" : "Save & publish"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
