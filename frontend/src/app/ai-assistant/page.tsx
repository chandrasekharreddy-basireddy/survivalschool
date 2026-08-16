"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";

interface Conversation { id: string; title: string }
interface AIMessage { id: string; role: string; content: string; provider: string }

const capabilities = [
  ["Explain", "Turn difficult ideas into clear, step-by-step explanations."],
  ["Solve", "Work through coding, maths, science, and logic problems with you."],
  ["Study", "Build revision plans, summaries, flashcards, and practice questions."],
  ["Review", "Give feedback on notes, answers, code, and project ideas."],
  ["Explore", "Compare concepts, connect ideas, and answer follow-up questions."],
  ["Create", "Draft examples, outlines, checklists, and learning resources."],
] as const;

export default function AiAssistantPage() {
  const { user, loading } = useAuth();
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AIMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typingId, setTypingId] = useState<string | null>(null);
  const [typedLength, setTypedLength] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<Conversation[]>("/ai/conversations").then((cs) => {
      setConversations(cs);
      if (cs.length > 0) setActiveId(cs[0].id);
    }).catch(() => setConversations([]));
  }, [user]);

  useEffect(() => {
    if (!activeId) return;
    setTypingId(null);
    setTypedLength(0);
    apiFetch<AIMessage[]>(`/ai/conversations/${activeId}/messages`).then(setMessages).catch(() => setMessages([]));
  }, [activeId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, typedLength]);

  useEffect(() => {
    if (!typingId) return;
    const message = messages.find((m) => m.id === typingId);
    if (!message || message.role !== "assistant") return;
    if (typedLength >= message.content.length) {
      setTypingId(null);
      return;
    }
    const timer = window.setTimeout(() => setTypedLength((n) => Math.min(n + 2, message.content.length)), 18);
    return () => window.clearTimeout(timer);
  }, [messages, typingId, typedLength]);

  const startNewConversation = async () => {
    const convo = await apiFetch<Conversation>("/ai/conversations", { method: "POST" });
    setConversations((prev) => [convo, ...(prev || [])]);
    setActiveId(convo.id);
    setMessages([]);
    setTypingId(null);
    setTypedLength(0);
  };

  const send = async () => {
    if (!input.trim()) return;
    let convoId = activeId;
    if (!convoId) {
      const convo = await apiFetch<Conversation>("/ai/conversations", { method: "POST" });
      setConversations((prev) => [convo, ...(prev || [])]);
      setActiveId(convo.id);
      convoId = convo.id;
    }
    const content = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: "user", content, provider: "" }]);
    setSending(true);
    setError(null);
    setTypingId(null);
    setTypedLength(0);
    try {
      const res = await apiFetch<{ conversation_id: string; reply: AIMessage }>(`/ai/conversations/${convoId}/messages`, {
        method: "POST",
        body: JSON.stringify({ content }),
      });
      setMessages((prev) => [...prev, res.reply]);
      setTypingId(res.reply.id);
      setTypedLength(0);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The AI tutor is unavailable right now.");
    } finally {
      setSending(false);
    }
  };

  if (loading) return <div className="page-frame text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="page-frame mx-auto max-w-md text-center">
        <p className="text-fg-muted">Sign in to use the AI tutor.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="page-frame">
      <header className="page-header">
        <p className="mb-2 text-[0.68rem] font-extrabold uppercase tracking-[0.18em] text-brand-400">AI LAB</p>
        <h1>Your study co-pilot</h1>
        <p className="mt-2 max-w-3xl text-sm text-fg-muted sm:text-base">
          Ask about what you are learning — coding, maths, science, study plans, summaries, projects, or anything else that helps you understand the subject better.
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <aside className="order-2 lg:order-1">
          <button onClick={startNewConversation} className="btn-secondary w-full">+ New conversation</button>
          <div className="mt-4 border-t border-ink-800 pt-3">
            <p className="mb-2 text-[0.68rem] font-extrabold uppercase tracking-[0.16em] text-fg-subtle">History</p>
            <ul className="space-y-1">
              {(conversations || []).map((c) => (
                <li key={c.id}>
                  <button
                    onClick={() => setActiveId(c.id)}
                    className={`w-full border-l-2 px-2.5 py-2 text-left text-sm transition-colors ${activeId === c.id ? "border-brand-500 bg-ink-900 text-fg" : "border-transparent text-fg-muted hover:border-ink-700 hover:bg-ink-900/70"}`}
                  >
                    <span className="block truncate">{c.title || "New conversation"}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </aside>

        <section className="order-1 min-w-0 lg:order-2">
          {messages.length === 0 && (
            <div className="mb-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <p className="text-[0.68rem] font-extrabold uppercase tracking-[0.16em] text-brand-400">What it can do</p>
                  <h2 className="mt-1">Useful first. Impressive second.</h2>
                </div>
                <span className="game-badge"><span className="status-dot" /> Ready</span>
              </div>
              <div className="ai-capability-grid">
                {capabilities.map(([title, copy]) => (
                  <div className="ai-capability" key={title}>
                    <strong>{title}</strong>
                    <span>{copy}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="sharp-surface flex min-h-[62vh] flex-col bg-ink-950/55 p-3 sm:p-4">
            <div className="flex items-center justify-between border-b border-ink-800 pb-3">
              <div>
                <p className="text-sm font-bold text-fg">Conversation</p>
                <p className="text-xs text-fg-subtle">Your responses appear as they are generated.</p>
              </div>
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-teal-300">Live</span>
            </div>

            <div className="flex-1 space-y-4 overflow-y-auto py-4">
              {messages.length === 0 ? (
                <div className="flex h-full min-h-56 items-center justify-center text-center">
                  <div className="max-w-md">
                    <div className="mx-auto mb-4 grid h-14 w-14 place-items-center border border-brand-500/50 bg-brand-500/10 text-brand-300">
                      <span className="text-xl font-black">SS</span>
                    </div>
                    <p className="text-base font-bold text-fg">Start with a real task.</p>
                    <p className="mt-1 text-sm text-fg-muted">Try “Explain recursion simply”, “Make me a 7-day study plan”, or “Why does photosynthesis need light?”</p>
                  </div>
                </div>
              ) : (
                messages.map((m) => {
                  const isTyping = m.id === typingId && m.role === "assistant";
                  const visibleContent = isTyping ? m.content.slice(0, typedLength) : m.content;
                  return m.role === "user" ? (
                    <div key={m.id} className="ml-auto max-w-[88%] border-l-2 border-brand-500 bg-brand-500/10 px-4 py-3 text-sm text-fg">
                      {m.content}
                    </div>
                  ) : (
                    <div key={m.id} className="max-w-[94%] border-l-2 border-teal-400 bg-ink-900/70 px-4 py-3 text-sm text-fg">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{visibleContent}</ReactMarkdown>
                      {isTyping && <span className="ml-1 inline-block animate-pulse text-brand-300">▌</span>}
                    </div>
                  );
                })
              )}
              <div ref={bottomRef} />
            </div>

            {error && <p className="border-l-2 border-red-400 bg-red-400/10 px-3 py-2 text-sm text-red-300">{error}</p>}

            <div className="mt-3 flex flex-col gap-2 border-t border-ink-800 pt-3 sm:flex-row">
              <input
                className="input"
                placeholder="Ask anything you’re learning…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !sending && send()}
                aria-label="Ask the AI tutor"
              />
              <button onClick={send} disabled={sending || !input.trim()} className="btn-primary shrink-0 sm:w-auto">
                {sending ? "Thinking…" : "Ask"}
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
