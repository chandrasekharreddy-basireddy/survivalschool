"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError, getAccessToken } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { PageLoader } from "@/components/PageLoader";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
const MAX_IMAGE_MB = 25;
const IMAGE_ACCEPT = "image/png,image/jpeg,image/gif,image/webp";

interface Conversation { id: string; title: string }
interface AIMessage { id: string; role: string; content: string; provider: string; image_url?: string | null }

const capabilities = [
  ["Explain", "Turn difficult ideas into clear, step-by-step explanations."],
  ["Solve", "Work through coding, maths, science, and logic problems with you."],
  ["Study", "Build revision plans, summaries, flashcards, and practice questions."],
  ["Review", "Give feedback on notes, answers, code, project ideas — or a photo of your work."],
] as const;

function AuthedImage({ url, alt }: { url: string; alt: string }) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    const token = getAccessToken();
    fetch(`${API_BASE}${url}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((r) => r.blob())
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);

  if (!src) return <div className="h-40 w-40 animate-pulse rounded-xl bg-ink-800" />;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt={alt} className="max-h-64 rounded-xl object-contain" />;
}

export default function AiAssistantPage() {
  const { user, loading } = useAuth();
  const toast = useToast();
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AIMessage[]>([]);
  const [input, setInput] = useState("");
  const [pendingImage, setPendingImage] = useState<File | null>(null);
  const [pendingImagePreview, setPendingImagePreview] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typingId, setTypingId] = useState<string | null>(null);
  const [typedLength, setTypedLength] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // send() sets this right before setActiveId() when it creates a brand-new
  // conversation for the message the caller is already in the middle of
  // sending — that conversation has no history to fetch yet, and send()
  // itself appends the optimistic user message + real reply once the POST
  // resolves. Without this guard, activeId changing also fires the effect
  // below, which fetches (empty) history and overwrites whatever send() has
  // already put in `messages` — a real race that was silently dropping the
  // just-sent message and its image.
  const skipNextHistoryFetchRef = useRef(false);
  // Tracks the live activeId inside send()'s closure — send() captures
  // activeId as a local at call time, but if the user clicks "+ New
  // conversation" while the request is still in flight, activeId moves on
  // without send() knowing. Comparing against this ref when the response
  // lands (rather than trusting the closed-over value) stops that reply
  // from being appended to whatever conversation happens to be open by
  // then instead of the one it actually belongs to.
  const activeIdRef = useRef<string | null>(null);
  useEffect(() => {
    activeIdRef.current = activeId;
  }, [activeId]);

  useEffect(() => {
    if (!user) return;
    apiFetch<Conversation[]>("/ai/conversations").then((cs) => {
      setConversations(cs);
      if (cs.length > 0) setActiveId(cs[0].id);
    }).catch(() => setConversations([]));
  }, [user]);

  useEffect(() => {
    if (!activeId) return;
    if (skipNextHistoryFetchRef.current) {
      skipNextHistoryFetchRef.current = false;
      return;
    }
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

  const onPickImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > MAX_IMAGE_MB * 1024 * 1024) {
      toast.show(`That image is too large. The limit is ${MAX_IMAGE_MB}MB.`, "error");
      return;
    }
    setPendingImage(file);
    setPendingImagePreview(URL.createObjectURL(file));
  };

  const clearPendingImage = () => {
    if (pendingImagePreview) URL.revokeObjectURL(pendingImagePreview);
    setPendingImage(null);
    setPendingImagePreview(null);
  };

  const send = async () => {
    if (!input.trim() && !pendingImage) return;
    let convoId = activeId;
    if (!convoId) {
      const convo = await apiFetch<Conversation>("/ai/conversations", { method: "POST" });
      setConversations((prev) => [convo, ...(prev || [])]);
      skipNextHistoryFetchRef.current = true;
      setActiveId(convo.id);
      convoId = convo.id;
    }
    const content = input.trim();
    const image = pendingImage;
    const imagePreview = pendingImagePreview;
    setInput("");
    setPendingImage(null);
    setPendingImagePreview(null);
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: "user", content, provider: "", image_url: imagePreview || undefined }]);
    setSending(true);
    setError(null);
    setTypingId(null);
    setTypedLength(0);
    try {
      let res: { conversation_id: string; reply: AIMessage };
      if (image) {
        const body = new FormData();
        body.append("content", content);
        body.append("file", image);
        res = await apiFetch(`/ai/conversations/${convoId}/messages/image`, { method: "POST", body });
      } else {
        res = await apiFetch(`/ai/conversations/${convoId}/messages`, { method: "POST", body: JSON.stringify({ content }) });
      }
      if (convoId === activeIdRef.current) {
        setMessages((prev) => [...prev, res.reply]);
        setTypingId(res.reply.id);
        setTypedLength(0);
      }
      // else: the user switched to a different (or new) conversation while
      // this was in flight. The reply is already saved server-side — it'll
      // show up the next time they open that conversation and its history
      // gets fetched, rather than getting appended to whatever's open now.
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The AI tutor is unavailable right now.");
    } finally {
      setSending(false);
    }
  };

  if (loading) return <div className="page-frame text-fg-muted"><PageLoader size="md" /></div>;
  if (!user) {
    return (
      <div className="page-frame mx-auto max-w-md text-center">
        <p className="text-fg-muted">Sign in to use the AI tutor.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-3.5rem)] max-w-6xl">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-ink-800 sm:flex">
        <div className="px-4 py-4">
          <button onClick={startNewConversation} className="btn-secondary w-full">+ New conversation</button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-4">
          {(conversations || []).map((c) => (
            <button
              key={c.id}
              onClick={() => setActiveId(c.id)}
              className={`block w-full truncate rounded-lg px-2.5 py-2 text-left text-sm transition-colors ${
                activeId === c.id ? "bg-ink-800 text-fg" : "text-fg-muted hover:bg-ink-900 hover:text-fg"
              }`}
            >
              {c.title || "New conversation"}
            </button>
          ))}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {messages.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
            <p className="text-lg font-semibold text-fg">Your study co-pilot</p>
            <p className="mt-1 max-w-md text-sm text-fg-muted">
              Ask about what you&apos;re learning, or attach a photo of a problem, diagram, or your own work.
            </p>
            <div className="mt-6 grid max-w-xl gap-3 sm:grid-cols-2">
              {capabilities.map(([title, copy]) => (
                <div key={title} className="card !p-3 text-left">
                  <p className="text-sm font-semibold text-fg">{title}</p>
                  <p className="mt-0.5 text-xs text-fg-muted">{copy}</p>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto px-6 py-6">
            <div className="mx-auto max-w-2xl space-y-4">
              {messages.map((m) => {
                const isTyping = m.id === typingId && m.role === "assistant";
                const visibleContent = isTyping ? m.content.slice(0, typedLength) : m.content;
                const isUser = m.role === "user";
                return (
                  <div key={m.id} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${isUser ? "bg-brand-600 text-white" : "bg-ink-800 text-fg"}`}>
                      {m.image_url && (
                        <div className="mb-2">
                          {m.image_url.startsWith("blob:") ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={m.image_url} alt="Attached" className="max-h-64 rounded-xl object-contain" />
                          ) : (
                            <AuthedImage url={m.image_url} alt="Attached" />
                          )}
                        </div>
                      )}
                      {isUser ? (
                        m.content && <p className="whitespace-pre-wrap">{m.content}</p>
                      ) : (
                        <div className="markdown-body">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{visibleContent}</ReactMarkdown>
                          {isTyping && <span className="ml-1 inline-block animate-pulse text-brand-300">▌</span>}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              <div ref={bottomRef} />
            </div>
          </div>
        )}

        {error && <p className="mx-6 rounded-lg border border-red-500/30 bg-red-500/5 px-3 py-2 text-sm text-red-700 dark:text-red-400">{error}</p>}

        <div className="border-t border-ink-800 px-6 py-4">
          <div className="mx-auto max-w-2xl">
            {pendingImagePreview && (
              <div className="mb-2 flex items-center gap-2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={pendingImagePreview} alt="" className="h-14 w-14 rounded-lg object-cover" />
                <button onClick={clearPendingImage} className="text-xs text-fg-subtle hover:text-fg">Remove</button>
              </div>
            )}
            <div className="flex items-end gap-2 rounded-2xl border border-ink-700 bg-ink-950 px-3 py-2">
              <input ref={fileInputRef} type="file" accept={IMAGE_ACCEPT} className="hidden" onChange={onPickImage} />
              <button
                onClick={() => fileInputRef.current?.click()}
                aria-label="Attach an image"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-fg-muted transition hover:bg-ink-800 hover:text-fg"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-4.5 w-4.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 0 1-6.364-6.364l10.94-10.94A3 3 0 1 1 19.5 7.372L8.552 18.32m.009-.01-.01.01" />
                </svg>
              </button>
              <textarea
                rows={1}
                className="max-h-32 flex-1 resize-none bg-transparent py-1.5 text-sm text-fg placeholder:text-fg-subtle focus:outline-none"
                placeholder="Ask anything you're learning…"
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  e.target.style.height = "auto";
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 128)}px`;
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !sending) {
                    e.preventDefault();
                    send();
                  }
                }}
              />
              <button
                onClick={send}
                disabled={sending || (!input.trim() && !pendingImage)}
                aria-label="Send"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white transition disabled:opacity-30"
              >
                {sending ? (
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                ) : (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 19.5 19.5 12 4.5 4.5v6l10 1.5-10 1.5v6Z" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
