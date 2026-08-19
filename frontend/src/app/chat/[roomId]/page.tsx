"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError, getAccessToken } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { ChatSocket, ChatEvent } from "@/lib/ws";
import { formatRelative } from "@/lib/format";

interface MessageOut {
  id: string;
  room_id: string;
  sender_id: string | null;
  body: string;
  created_at: string;
  is_deleted: boolean;
}
interface RoomOut { id: string; name: string; room_type: string; other_user_id: string | null; other_user_name: string | null }

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase() || "?";
}

export default function ChatRoomPage() {
  const params = useParams<{ roomId: string }>();
  const { user, loading } = useAuth();
  const toast = useToast();
  const [room, setRoom] = useState<RoomOut | null>(null);
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [input, setInput] = useState("");
  const [typingUsers, setTypingUsers] = useState<Set<string>>(new Set());
  const [connected, setConnected] = useState(false);
  const [seenBy, setSeenBy] = useState<Record<string, Set<string>>>({});
  const [canModerate, setCanModerate] = useState(false);
  const socketRef = useRef<ChatSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const readSentRef = useRef<Set<string>>(new Set());
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setCanModerate(!!user?.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r)));
  }, [user]);

  useEffect(() => {
    if (!user) return;
    apiFetch<RoomOut[]>("/chat/rooms").then((list) => setRoom(list.find((r) => r.id === params.roomId) || null)).catch(() => {});
    apiFetch<MessageOut[]>(`/chat/rooms/${params.roomId}/messages?limit=100`).then(setMessages).catch(() => setMessages([]));

    const token = getAccessToken();
    if (!token) return;
    const socket = new ChatSocket(params.roomId, token);
    socketRef.current = socket;
    socket.connect();
    setConnected(true);

    const unsubscribe = socket.on((evt: ChatEvent) => {
      if (evt.event === "chat.message") {
        setMessages((prev) => [...prev, { id: evt.id, room_id: evt.room_id, sender_id: evt.sender_id, body: evt.body, created_at: evt.created_at, is_deleted: false }]);
        if (evt.sender_id && evt.sender_id !== user.id) {
          socketRef.current?.sendRead(evt.id);
        }
      } else if (evt.event === "chat.typing") {
        setTypingUsers((prev) => new Set(prev).add(evt.user_id));
        setTimeout(() => setTypingUsers((prev) => { const next = new Set(prev); next.delete(evt.user_id); return next; }), 3000);
      } else if (evt.event === "chat.read") {
        setSeenBy((prev) => {
          const next = { ...prev };
          next[evt.message_id] = new Set(next[evt.message_id] || []).add(evt.user_id);
          return next;
        });
      }
    });

    return () => {
      unsubscribe();
      socket.close();
      setConnected(false);
    };
  }, [user, params.roomId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (!user || !connected) return;
    for (const m of messages) {
      if (m.sender_id && m.sender_id !== user.id && !m.is_deleted && !readSentRef.current.has(m.id)) {
        readSentRef.current.add(m.id);
        socketRef.current?.sendRead(m.id);
      }
    }
  }, [messages, user, connected]);

  const send = () => {
    if (!input.trim() || !socketRef.current) return;
    socketRef.current.sendMessage(input);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const moderate = async (messageId: string) => {
    try {
      await apiFetch(`/chat/rooms/${params.roomId}/messages/${messageId}/moderate`, { method: "POST" });
      setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, is_deleted: true } : m)));
      toast.show("Message removed.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't remove that message.", "error");
    }
  };

  if (loading) return <div className="flex h-full items-center justify-center text-fg-muted">Loading…</div>;
  if (!user) return null;

  const headerName = room ? (room.room_type === "direct" ? room.other_user_name || room.name : room.name) : "";

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-ink-800 px-6 py-3.5">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-800 text-xs font-semibold text-fg-muted">
          {headerName ? initials(headerName) : "…"}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-fg">{headerName || "Conversation"}</p>
          {typingUsers.size > 0 ? (
            <p className="text-xs text-brand-600 dark:text-brand-400">typing…</p>
          ) : (
            <p className={`text-xs ${connected ? "text-emerald-700 dark:text-emerald-400" : "text-fg-subtle"}`}>{connected ? "Active now" : "Connecting…"}</p>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-2xl space-y-1">
          {messages.length === 0 ? (
            <p className="py-10 text-center text-sm text-fg-subtle">No messages yet — say hello.</p>
          ) : (
            (() => {
              const visible = messages.filter((m) => !m.is_deleted);
              const lastOwnId = [...visible].reverse().find((m) => m.sender_id === user.id)?.id;
              return visible.map((m, i) => {
                const isOwn = m.sender_id === user.id;
                const seenByOthers = (seenBy[m.id]?.size || 0) > 0;
                const prev = visible[i - 1];
                const groupedWithPrev = prev && prev.sender_id === m.sender_id && !prev.is_deleted;
                return (
                  <div key={m.id} className={`group flex ${isOwn ? "justify-end" : "justify-start"} ${groupedWithPrev ? "mt-0.5" : "mt-3"}`}>
                    <div className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm leading-relaxed ${isOwn ? "bg-brand-600 text-white" : "bg-ink-800 text-fg"}`}>
                      <p className="whitespace-pre-wrap">{m.body}</p>
                    </div>
                    {!isOwn && canModerate && (
                      <button
                        onClick={() => moderate(m.id)}
                        className="ml-2 self-center text-[10px] text-fg-subtle opacity-0 transition group-hover:opacity-70 hover:!opacity-100"
                        title="Remove message"
                      >
                        Remove
                      </button>
                    )}
                    {isOwn && m.id === lastOwnId && (
                      <p className="ml-2 self-end text-[10px] text-fg-subtle">
                        {formatRelative(m.created_at)}{seenByOthers && " · Seen"}
                      </p>
                    )}
                  </div>
                );
              });
            })()
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t border-ink-800 px-6 py-4">
        <div className="mx-auto flex max-w-2xl items-end gap-2 rounded-2xl border border-ink-700 bg-ink-950 px-3 py-2">
          <textarea
            ref={textareaRef}
            rows={1}
            className="max-h-32 flex-1 resize-none bg-transparent py-1.5 text-sm text-fg placeholder:text-fg-subtle focus:outline-none"
            placeholder="Message…"
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              socketRef.current?.sendTyping();
              e.target.style.height = "auto";
              e.target.style.height = `${Math.min(e.target.scrollHeight, 128)}px`;
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <button
            onClick={send}
            disabled={!input.trim()}
            aria-label="Send message"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white transition disabled:opacity-30"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 19.5 19.5 12 4.5 4.5v6l10 1.5-10 1.5v6Z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
