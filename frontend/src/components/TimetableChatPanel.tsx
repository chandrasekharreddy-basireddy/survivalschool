"use client";

import { useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import { PageLoader } from "@/components/PageLoader";

interface ChatTurn {
  question: string;
  answer: string;
}

interface ChatResponse {
  answer: string;
  provider: string;
}

/** A small collapsible Q&A panel scoped strictly to the student's own
 * already-parsed schedule — the backend (POST /timetable/me/chat) hands the
 * AI only that real data and instructs it never to invent a class, time,
 * room, or teacher beyond it. Deliberately stateless on the client (no
 * conversation persistence): each question is answered fresh against the
 * live schedule, same as the rest of this page. */
export function TimetableChatPanel() {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = question.trim();
    if (!q || asking) return;
    setAsking(true);
    setError(null);
    try {
      const result = await apiFetch<ChatResponse>("/timetable/me/chat", {
        method: "POST",
        body: JSON.stringify({ question: q }),
      });
      setTurns((prev) => [...prev, { question: q, answer: result.answer }]);
      setQuestion("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the timetable assistant.");
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className="card mt-4 !p-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-left"
        aria-expanded={open}
      >
        <span className="text-sm font-semibold text-fg">Ask about your schedule</span>
        <span className="text-xs text-fg-subtle">{open ? "Hide" : "Ask a question"}</span>
      </button>

      {open && (
        <div className="mt-3">
          <p className="text-xs text-fg-muted">
            Answers come only from your own parsed timetable — not general knowledge. Try &quot;What&apos;s my next
            class?&quot; or &quot;When is my Friday free?&quot;
          </p>

          {turns.length > 0 && (
            <div className="mt-3 max-h-64 space-y-3 overflow-y-auto rounded-lg border border-ink-700 bg-ink-950 p-3">
              {turns.map((t, i) => (
                <div key={i} className="space-y-1">
                  <p className="text-xs font-medium text-fg-subtle">You: {t.question}</p>
                  <p className="text-sm text-fg">{t.answer}</p>
                </div>
              ))}
            </div>
          )}

          {error && <p className="mt-2 text-xs text-red-700 dark:text-red-400">{error}</p>}

          <form onSubmit={ask} className="mt-3 flex gap-2">
            <input
              type="text"
              className="input flex-1"
              placeholder="Ask a question…"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={asking}
              maxLength={500}
            />
            <button type="submit" className="btn-primary shrink-0" disabled={asking || !question.trim()}>
              {asking ? <PageLoader size="sm" label="" /> : "Ask"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

export default TimetableChatPanel;
