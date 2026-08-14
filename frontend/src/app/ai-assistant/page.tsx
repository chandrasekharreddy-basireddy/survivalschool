"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
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
    apiFetch<AIMessage[]>(`/ai/conversations/${activeId}/messages`).then(setMessages).catch(() => setMessages([]));
  }, [activeId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const startNewConversation = async () => {
    const convo = await apiFetch<Conversation>("/ai/conversations", { method: "POST" });
    setConversations((prev) => [convo, ...(prev || [])]);
    setActiveId(convo.id);
    setMessages([]);
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
    const content = input;
    setInput("");
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: "user", content, provider: "" }]);
    setSending(true);
    setError(null);
    try {
      const res = await apiFetch<{ conversation_id: string; reply: AIMessage }>(`/ai/conversations/${convoId}/messages`, {
        method: "POST",
        body: JSON.stringify({ content }),
      });
      setMessages((prev) => [...prev, res.reply]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The AI tutor is unavailable right now.");
    } finally {
      setSending(false);
    }
  };

  if (loading) return <div className="mx-auto max-w-4xl px-6 py-16 text-slate-400">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-slate-300">Sign in to chat with the AI tutor.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-5xl gap-6 px-6 py-10">
      <aside className="hidden w-56 shrink-0 sm:block">
        <button onClick={startNewConversation} className="btn-secondary w-full !py-2 text-sm">+ New chat</button>
        <ul className="mt-4 space-y-1">
          {(conversations || []).map((c) => (
            <li key={c.id}>
              <button
                onClick={() => setActiveId(c.id)}
                className={`w-full truncate rounded-lg px-3 py-2 text-left text-sm ${activeId === c.id ? "bg-ink-800 text-white" : "text-slate-400 hover:bg-ink-900"}`}
              >
                {c.title || "New conversation"}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <div className="flex min-h-[70vh] flex-1 flex-col">
        <h1 className="text-xl font-bold text-white">AI Tutor</h1>
        <p className="mt-1 text-sm text-slate-500">
          Ask questions about course material. It won&apos;t hand you exam answers directly — it guides you toward understanding instead.
        </p>

        <div className="card mt-4 flex-1 space-y-3 overflow-y-auto">
          {messages.length === 0 ? (
            <p className="text-sm text-slate-500">Ask anything to get started.</p>
          ) : (
            messages.map((m) => (
              <div key={m.id} className={`max-w-[80%] rounded-lg px-4 py-2.5 text-sm ${m.role === "user" ? "ml-auto bg-brand-500 text-white" : "bg-ink-800 text-slate-200"}`}>
                {m.content}
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>

        {error && <p className="mt-2 text-sm text-red-400">{error}</p>}

        <div className="mt-4 flex gap-3">
          <input
            className="input"
            placeholder="Ask the AI tutor…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !sending && send()}
          />
          <button onClick={send} disabled={sending || !input.trim()} className="btn-primary shrink-0">
            {sending ? "…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
