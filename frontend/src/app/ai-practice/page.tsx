"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatDate } from "@/lib/format";
import { PageLoader } from "@/components/PageLoader";

interface HistoryItem { id: string; subject: string; question_count: number; submitted_at: string | null; score_percent: number | null; created_at: string }

export default function AIPracticeHomePage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const [subject, setSubject] = useState("");
  const [count, setCount] = useState(5);
  const [generating, setGenerating] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);

  useEffect(() => {
    if (!user) return;
    apiFetch<HistoryItem[]>("/ai-practice/me/sessions").then(setHistory).catch(() => setHistory([]));
  }, [user]);

  const generate = async () => {
    if (!subject.trim()) return;
    setGenerating(true);
    try {
      const session = await apiFetch<{ id: string }>("/ai-practice/sessions", {
        method: "POST",
        body: JSON.stringify({ subject, question_count: count }),
      });
      router.push(`/ai-practice/${session.id}`);
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't generate practice questions.", "error");
    } finally {
      setGenerating(false);
    }
  };

  if (loading) return <div className="mx-auto max-w-2xl px-6 py-16 text-fg-muted"><PageLoader size="md" /></div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to generate AI practice questions.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">AI practice questions</h1>
      <p className="mt-1 text-sm text-fg-muted">
        Pick any subject and get a fresh set of AI-generated multiple-choice questions to practice with. These are for learning only —
        they&apos;re kept completely separate from your instructors&apos; real question bank, never count toward a grade or certificate, and never award points.
      </p>

      <div className="card mt-6 space-y-4">
        <div>
          <label className="label">Subject</label>
          <input className="input" placeholder="e.g. Cellular respiration, Python decorators, WWII timeline…" value={subject} onChange={(e) => setSubject(e.target.value)} />
        </div>
        <div>
          <label className="label">Number of questions</label>
          <select className="input" value={count} onChange={(e) => setCount(Number(e.target.value))}>
            {[3, 5, 8, 10, 15].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <button onClick={generate} disabled={generating || !subject.trim()} className="btn-primary w-full">
          {generating ? "Generating…" : "Generate practice questions"}
        </button>
      </div>

      {history.length > 0 && (
        <div className="mt-8">
          <h2 className="font-semibold text-fg">Recent sessions</h2>
          <ul className="mt-3 divide-y divide-ink-800">
            {history.slice(0, 10).map((h) => (
              <li key={h.id} className="flex items-center justify-between py-2.5 text-sm">
                <Link href={`/ai-practice/${h.id}`} className="text-fg hover:text-brand-400">{h.subject}</Link>
                <span className="text-fg-subtle">
                  {h.score_percent != null ? `${h.score_percent}%` : "in progress"} · {formatDate(h.created_at)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
