"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";

interface Conversation { id: string; title: string }
interface AIMessage { id: string; role: string; content: string; provider: string }

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

  if (loading) return <div className="mx-auto max-w-4xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to chat with the AI tutor.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-5xl gap-5 px-4 py-7 sm:px-5 lg:px-6">
      <aside className="hidden w-56 shrink-0 sm:block">
        <button onClick={startNewConversation} className="btn-secondary w-full !py-2 text-sm">+ New chat</button>
        <ul className="mt-3 space-y-1">
          {(conversations || []).map((c) => (
            <li key={c.id}>
              <button
                onClick={() => setActiveId(c.id)}
                className={`w-full truncate rounded-lg px-3 py-2 text-left text-sm ${activeId === c.id ? "bg-ink-800 text-fg" : "text-fg-muted hover:bg-ink-900"}`}
              >
                {c.title || "New conversation"}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <div className="flex min-h-[70vh] flex-1 flex-col">
        <h1 className="text-xl font-bold text-fg">AI Tutor</h1>
        <p className="mt-1 text-sm text-fg-subtle">
          Ask coding and software-development questions. The tutor stays focused on programming, debugging, algorithms, and related technical topics.
        </p>

        <div className="card mt-3 flex-1 space-y-3 overflow-y-auto">
          {messages.length === 0 ? (
            <p className="text-sm text-fg-subtle">Ask a coding question to get started.</p>
          ) : (
            messages.map((m) => {
              const isTyping = m.id === typingId && m.role === "assistant";
              const visibleContent = isTyping ? m.content.slice(0, typedLength) : m.content;
              return m.role === "user" ? (
                <div key={m.id} className="ml-auto max-w-[80%] whitespace-pre-wrap rounded-lg bg-brand-500 px-4 py-2.5 text-sm text-white">
                  {m.content}
                </div>
              ) : (
                <div key={m.id} className="markdown-body max-w-[92%] rounded-lg bg-ink-800 px-4 py-3 text-sm text-fg">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{visibleContent}</ReactMarkdown>
                  {isTyping && <span className="ml-1 inline-block animate-pulse">▌</span>}
                </div>
              );
            })
          )}
          <div ref={bottomRef} />
        </div>

        {error && <p className="mt-2 text-sm text-red-700 dark:text-red-400">{error}</p>}

        <div className="mt-3 flex gap-2">
          <input
            className="input"
            placeholder="Ask a coding question…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !sending && send()}
          />
          <button onClick={send} disabled={sending || !input.trim()} className="btn-primary shrink-0">
            {sending ? "Thinking…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
