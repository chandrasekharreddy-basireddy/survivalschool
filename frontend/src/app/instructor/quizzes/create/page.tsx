"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

export default function CreateQuizPage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-2xl px-6 py-16 text-slate-400">Loading…</div>}>
      <CreateQuizForm />
    </Suspense>
  );
}

interface DraftOption { text: string; is_correct: boolean }
interface DraftQuestion {
  prompt: string;
  question_type: "single" | "multiple" | "true_false" | "short_answer";
  points: number;
  options: DraftOption[];
}

function emptyQuestion(): DraftQuestion {
  return { prompt: "", question_type: "single", points: 1, options: [{ text: "", is_correct: true }, { text: "", is_correct: false }] };
}

function CreateQuizForm() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const courseId = searchParams.get("course_id") || "";
  const toast = useToast();

  const [title, setTitle] = useState("");
  const [maxAttempts, setMaxAttempts] = useState(3);
  const [passScore, setPassScore] = useState(70);
  const [timeLimitMin, setTimeLimitMin] = useState<number | "">("");
  const [questions, setQuestions] = useState<DraftQuestion[]>([emptyQuestion()]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (loading) return <div className="mx-auto max-w-2xl px-6 py-16 text-slate-400">Loading…</div>;
  if (!user || !user.roles.some((r) => ["INSTRUCTOR", "ADMIN", "SUPER_ADMIN"].includes(r))) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-slate-300">This area is for instructors.</p>
        <Link href="/dashboard" className="btn-secondary mt-6 inline-flex">Back to dashboard</Link>
      </div>
    );
  }
  if (!courseId) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-slate-300">Open this page from a course&apos;s manage screen so it knows which course to attach the quiz to.</p>
        <Link href="/instructor/courses" className="btn-secondary mt-6 inline-flex">Your courses</Link>
      </div>
    );
  }

  const updateQuestion = (idx: number, patch: Partial<DraftQuestion>) => {
    setQuestions((prev) => prev.map((q, i) => (i === idx ? { ...q, ...patch } : q)));
  };
  const updateOption = (qIdx: number, oIdx: number, patch: Partial<DraftOption>) => {
    setQuestions((prev) => prev.map((q, i) => {
      if (i !== qIdx) return q;
      const options = q.options.map((o, j) => {
        if (j !== oIdx) return patch.is_correct !== undefined && (q.question_type === "single" || q.question_type === "true_false") ? { ...o, is_correct: false } : o;
        return { ...o, ...patch };
      });
      return { ...q, options };
    }));
  };

  const isValid = title.trim().length > 0 && questions.every((q) =>
    q.prompt.trim().length > 0 &&
    (q.question_type === "short_answer" || (q.options.filter((o) => o.text.trim()).length >= 2 && q.options.some((o) => o.is_correct)))
  );

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      const questionIds: string[] = [];
      for (const q of questions) {
        const created = await apiFetch<{ id: string }>("/questions", {
          method: "POST",
          body: JSON.stringify({
            course_id: courseId, prompt: q.prompt, question_type: q.question_type, points: q.points,
            options: q.question_type === "short_answer" ? [] : q.options.filter((o) => o.text.trim()).map((o, idx) => ({ text: o.text, is_correct: o.is_correct, order_index: idx })),
          }),
        });
        questionIds.push(created.id);
      }
      const quiz = await apiFetch<{ id: string }>("/quizzes", {
        method: "POST",
        body: JSON.stringify({
          course_id: courseId, title, max_attempts: maxAttempts, pass_score_percent: passScore,
          time_limit_seconds: timeLimitMin ? Number(timeLimitMin) * 60 : null, question_ids: questionIds,
        }),
      });
      await apiFetch(`/quizzes/${quiz.id}/publish`, { method: "POST" });
      toast.show("Quiz created and published.", "success");
      router.push(`/instructor/courses/${courseId}/edit`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create the quiz.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold text-white">Create a quiz</h1>

      <div className="card mt-6 space-y-4">
        <div>
          <label className="label">Quiz title</label>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} required />
        </div>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="label">Max attempts</label>
            <input type="number" min={1} className="input" value={maxAttempts} onChange={(e) => setMaxAttempts(Number(e.target.value))} />
          </div>
          <div>
            <label className="label">Pass score %</label>
            <input type="number" min={0} max={100} className="input" value={passScore} onChange={(e) => setPassScore(Number(e.target.value))} />
          </div>
          <div>
            <label className="label">Time limit (min, optional)</label>
            <input type="number" min={1} className="input" value={timeLimitMin} onChange={(e) => setTimeLimitMin(e.target.value ? Number(e.target.value) : "")} />
          </div>
        </div>
      </div>

      <h2 className="mt-8 font-semibold text-white">Questions</h2>
      <div className="mt-4 space-y-4">
        {questions.map((q, qIdx) => (
          <div key={qIdx} className="card">
            <div className="flex items-center justify-between gap-3">
              <input
                className="input flex-1"
                placeholder="Question prompt"
                value={q.prompt}
                onChange={(e) => updateQuestion(qIdx, { prompt: e.target.value })}
              />
              <select className="input w-40" value={q.question_type} onChange={(e) => updateQuestion(qIdx, { question_type: e.target.value as DraftQuestion["question_type"] })}>
                <option value="single">Single choice</option>
                <option value="multiple">Multiple choice</option>
                <option value="true_false">True / False</option>
              </select>
              {questions.length > 1 && (
                <button onClick={() => setQuestions((prev) => prev.filter((_, i) => i !== qIdx))} className="text-sm text-red-400 hover:underline">Remove</button>
              )}
            </div>

            <div className="mt-3 space-y-2">
              {(q.question_type === "true_false" ? [{ text: "True", is_correct: q.options[0]?.is_correct ?? true }, { text: "False", is_correct: q.options[1]?.is_correct ?? false }] : q.options).map((opt, oIdx) => (
                <div key={oIdx} className="flex items-center gap-2">
                  <input
                    type={q.question_type === "multiple" ? "checkbox" : "radio"}
                    name={`correct-${qIdx}`}
                    checked={opt.is_correct}
                    onChange={(e) => updateOption(qIdx, oIdx, { is_correct: e.target.checked })}
                    className="accent-brand-500"
                  />
                  {q.question_type === "true_false" ? (
                    <span className="text-sm text-slate-300">{opt.text}</span>
                  ) : (
                    <input
                      className="input !py-1.5 text-sm"
                      placeholder={`Option ${oIdx + 1}`}
                      value={opt.text}
                      onChange={(e) => updateOption(qIdx, oIdx, { text: e.target.value })}
                    />
                  )}
                </div>
              ))}
              {q.question_type !== "true_false" && (
                <button
                  onClick={() => updateQuestion(qIdx, { options: [...q.options, { text: "", is_correct: false }] })}
                  className="text-xs text-brand-400 hover:underline"
                >
                  + Add option
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <button onClick={() => setQuestions((prev) => [...prev, emptyQuestion()])} className="btn-secondary mt-4">+ Add question</button>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      <button onClick={submit} disabled={saving || !isValid} className="btn-primary mt-6 w-full">
        {saving ? "Creating…" : "Create & publish quiz"}
      </button>
    </div>
  );
}
