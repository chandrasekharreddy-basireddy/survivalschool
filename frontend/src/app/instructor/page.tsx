"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useRole } from "@/lib/use-role";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface Subject { id: string; name: string; slug: string }
interface Topic { id: string; name: string; slug: string }

const QUESTION_TYPES = [
  { value: "single", label: "Single answer" },
  { value: "multiple", label: "Multiple answer" },
  { value: "true_false", label: "True / False" },
];

export default function InstructorPage() {
  const { user } = useAuth();
  const { isAdmin } = useRole();
  const toast = useToast();

  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [subjectId, setSubjectId] = useState("");
  const [topicId, setTopicId] = useState("");

  const [newSubjectName, setNewSubjectName] = useState("");
  const [newTopicName, setNewTopicName] = useState("");
  const [creatingTaxonomy, setCreatingTaxonomy] = useState(false);

  const [prompt, setPrompt] = useState("");
  const [questionType, setQuestionType] = useState("single");
  const [options, setOptions] = useState([
    { text: "", is_correct: true },
    { text: "", is_correct: false },
  ]);
  const [savingQuestion, setSavingQuestion] = useState(false);

  const loadSubjects = () => apiFetch<Subject[]>("/subjects", { auth: false }).then(setSubjects).catch(() => setSubjects([]));

  useEffect(() => { loadSubjects(); }, []);

  useEffect(() => {
    if (!subjectId) { setTopics([]); setTopicId(""); return; }
    apiFetch<Topic[]>(`/subjects/${subjectId}/topics`, { auth: false }).then((t) => { setTopics(t); setTopicId(""); }).catch(() => setTopics([]));
  }, [subjectId]);

  const slugify = (s: string) => s.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "").slice(0, 140);

  const createSubject = async () => {
    if (!newSubjectName.trim()) return;
    setCreatingTaxonomy(true);
    try {
      await apiFetch("/subjects", { method: "POST", body: JSON.stringify({ name: newSubjectName.trim(), slug: slugify(newSubjectName) }) });
      setNewSubjectName("");
      await loadSubjects();
      toast.show("Subject created.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't create subject.", "error");
    } finally {
      setCreatingTaxonomy(false);
    }
  };

  const createTopic = async () => {
    if (!newTopicName.trim() || !subjectId) return;
    setCreatingTaxonomy(true);
    try {
      const t = await apiFetch<Topic>(`/subjects/${subjectId}/topics`, { method: "POST", body: JSON.stringify({ name: newTopicName.trim(), slug: slugify(newTopicName) }) });
      setNewTopicName("");
      setTopics((prev) => [...prev, t]);
      toast.show("Topic created.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't create topic.", "error");
    } finally {
      setCreatingTaxonomy(false);
    }
  };

  const setOptionText = (idx: number, text: string) => setOptions((prev) => prev.map((o, i) => (i === idx ? { ...o, text } : o)));
  const setOptionCorrect = (idx: number, checked: boolean) =>
    setOptions((prev) => prev.map((o, i) => {
      if (questionType === "multiple") return i === idx ? { ...o, is_correct: checked } : o;
      return { ...o, is_correct: i === idx };
    }));
  const addOption = () => setOptions((prev) => [...prev, { text: "", is_correct: false }]);
  const removeOption = (idx: number) => setOptions((prev) => prev.filter((_, i) => i !== idx));

  const createQuestion = async () => {
    if (!subjectId || !topicId || !prompt.trim()) {
      toast.show("Pick a subject, topic, and enter a prompt first.", "error");
      return;
    }
    const cleanOptions = options.filter((o) => o.text.trim());
    if (questionType !== "short_answer" && cleanOptions.length < 2) {
      toast.show("Add at least two options.", "error");
      return;
    }
    setSavingQuestion(true);
    try {
      await apiFetch("/questions", {
        method: "POST",
        body: JSON.stringify({
          subject_id: subjectId, topic_id: topicId, prompt: prompt.trim(), question_type: questionType, points: 1,
          options: cleanOptions.map((o, idx) => ({ text: o.text.trim(), is_correct: o.is_correct, order_index: idx })),
        }),
      });
      setPrompt("");
      setOptions([{ text: "", is_correct: true }, { text: "", is_correct: false }]);
      toast.show("Question added to the bank.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't save that question.", "error");
    } finally {
      setSavingQuestion(false);
    }
  };

  const [importFile, setImportFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<{ total_rows: number; valid_rows: number; error_rows: number; committed: boolean; inserted_count: number; rows: { row_number: number; error: string | null }[] } | null>(null);

  const runImport = async (commit: boolean) => {
    if (!importFile || !subjectId || !topicId) {
      toast.show("Pick a subject, topic, and a file first.", "error");
      return;
    }
    setImporting(true);
    setImportResult(null);
    try {
      const form = new FormData();
      form.append("file", importFile);
      const result = await apiFetch<typeof importResult>(
        `/questions/bulk-import?subject_id=${subjectId}&topic_id=${topicId}&dry_run=${commit ? "false" : "true"}`,
        { method: "POST", body: form, timeoutMs: 60000 }
      );
      setImportResult(result);
      if (commit && result?.committed) toast.show(`Imported ${result.inserted_count} questions.`, "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Import failed.", "error");
    } finally {
      setImporting(false);
    }
  };

  if (!user) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Question bank</h1>
      <p className="mt-1 text-sm text-fg-muted">
        Add real, human-authored questions to the shared bank — every AI Weekly Exam, Elimination Battle, and practice
        session draws from this pool alongside AI-generated ones.
      </p>

      {isAdmin && (
        <div className="card mt-6">
          <h2 className="font-semibold text-fg">Subjects &amp; topics</h2>
          <p className="mt-1 text-xs text-fg-subtle">Only admins can create new subjects and topics.</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <input className="input flex-1" placeholder="New subject name" value={newSubjectName} onChange={(e) => setNewSubjectName(e.target.value)} />
            <button onClick={createSubject} disabled={creatingTaxonomy || !newSubjectName.trim()} className="btn-secondary shrink-0">Add subject</button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <select className="input" value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
              <option value="">Pick a subject…</option>
              {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <input className="input flex-1" placeholder="New topic name" value={newTopicName} onChange={(e) => setNewTopicName(e.target.value)} disabled={!subjectId} />
            <button onClick={createTopic} disabled={creatingTaxonomy || !subjectId || !newTopicName.trim()} className="btn-secondary shrink-0">Add topic</button>
          </div>
        </div>
      )}

      <div className="card mt-6">
        <h2 className="font-semibold text-fg">Add a question</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <select className="input" value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
            <option value="">Subject…</option>
            {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <select className="input" value={topicId} onChange={(e) => setTopicId(e.target.value)} disabled={!subjectId}>
            <option value="">Topic…</option>
            {topics.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </div>

        <textarea className="input mt-3 min-h-20" placeholder="Question prompt" value={prompt} onChange={(e) => setPrompt(e.target.value)} />

        <select className="input mt-3" value={questionType} onChange={(e) => { setQuestionType(e.target.value); setOptions((prev) => prev.map((o, i) => ({ ...o, is_correct: i === 0 }))); }}>
          {QUESTION_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>

        <div className="mt-3 space-y-2">
          {options.map((o, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input
                type={questionType === "multiple" ? "checkbox" : "radio"}
                name="correct-option" checked={o.is_correct} onChange={(e) => setOptionCorrect(idx, e.target.checked)} className="accent-brand-500"
              />
              <input className="input flex-1" placeholder={`Option ${idx + 1}`} value={o.text} onChange={(e) => setOptionText(idx, e.target.value)} />
              {options.length > 2 && <button onClick={() => removeOption(idx)} className="text-xs text-fg-subtle hover:text-red-500">Remove</button>}
            </div>
          ))}
          {options.length < 8 && <button onClick={addOption} className="text-xs text-brand-600 dark:text-brand-400 hover:underline">+ Add option</button>}
        </div>

        <button onClick={createQuestion} disabled={savingQuestion} className="btn-primary mt-4">{savingQuestion ? "Saving…" : "Add question"}</button>
      </div>

      <div className="card mt-6">
        <h2 className="font-semibold text-fg">Bulk import (CSV / XLSX)</h2>
        <p className="mt-1 text-xs text-fg-subtle">All-or-nothing: nothing is inserted unless every row in the file is valid.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <select className="input" value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
            <option value="">Subject…</option>
            {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <select className="input" value={topicId} onChange={(e) => setTopicId(e.target.value)} disabled={!subjectId}>
            <option value="">Topic…</option>
            {topics.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </div>
        <input type="file" accept=".csv,.xlsx" onChange={(e) => setImportFile(e.target.files?.[0] || null)} className="input mt-3" />
        <div className="mt-3 flex gap-3">
          <button onClick={() => runImport(false)} disabled={importing || !importFile} className="btn-secondary">{importing ? "Checking…" : "Preview"}</button>
          <button onClick={() => runImport(true)} disabled={importing || !importFile || !importResult || importResult.error_rows > 0} className="btn-primary">
            {importing ? "Importing…" : "Commit import"}
          </button>
        </div>
        {importResult && (
          <div className="mt-4 rounded-lg border border-ink-700 p-3 text-sm">
            <p className="text-fg">{importResult.total_rows} rows · {importResult.valid_rows} valid · {importResult.error_rows} errors</p>
            {importResult.committed && <p className="mt-1 text-emerald-600 dark:text-emerald-400">Inserted {importResult.inserted_count} questions.</p>}
            {importResult.rows.filter((r) => r.error).slice(0, 10).map((r) => (
              <p key={r.row_number} className="mt-1 text-xs text-red-600 dark:text-red-400">Row {r.row_number}: {r.error}</p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
