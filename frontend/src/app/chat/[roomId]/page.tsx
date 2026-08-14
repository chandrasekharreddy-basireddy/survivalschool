"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
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

export default function ChatRoomPage() {
  const params = useParams<{ roomId: string }>();
  const { user, loading } = useAuth();
  const toast = useToast();
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [input, setInput] = useState("");
  const [typingUsers, setTypingUsers] = useState<Set<string>>(new Set());
  const [connected, setConnected] = useState(false);
  const [seenBy, setSeenBy] = useState<Record<string, Set<string>>>({});
  const [canModerate, setCanModerate] = useState(false);
  const socketRef = useRef<ChatSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const readSentRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    setCanModerate(!!user?.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r)));
  }, [user]);

  useEffect(() => {
    if (!user) return;
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
        // A message from someone else just arrived while we're looking at
        // the room — mark it read immediately (best-effort, non-blocking).
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

  // Mark every message from someone else as read once it's loaded/rendered —
  // this is what actually closes the read-receipt loop for messages that
  // were already on the page before this client connected (history fetch),
  // not just ones that arrive live.
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

  if (loading) return <div className="mx-auto max-w-2xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to use chat.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-4.5rem)] max-w-2xl flex-col px-6 py-6">
      <div className="flex items-center justify-between">
        <Link href="/chat" className="text-sm text-fg-muted hover:text-fg">&larr; All rooms</Link>
        <span className={`text-xs ${connected ? "text-emerald-400" : "text-fg-subtle"}`}>{connected ? "Live" : "Connecting…"}</span>
      </div>

      <div className="card mt-4 flex-1 space-y-3 overflow-y-auto">
        {messages.length === 0 ? (
          <p className="text-sm text-fg-subtle">No messages yet — say hello.</p>
        ) : (
          (() => {
            const visible = messages.filter((m) => !m.is_deleted);
            const lastOwnId = [...visible].reverse().find((m) => m.sender_id === user.id)?.id;
            return visible.map((m) => {
              const isOwn = m.sender_id === user.id;
              const seenByOthers = (seenBy[m.id]?.size || 0) > 0;
              return (
                <div key={m.id} className={`group max-w-[75%] rounded-lg px-4 py-2 text-sm ${isOwn ? "ml-auto bg-brand-500 text-white" : "bg-ink-800 text-fg"}`}>
                  <div className="flex items-start justify-between gap-2">
                    <p className="flex-1">{m.body}</p>
                    {!isOwn && canModerate && (
                      <button
                        onClick={() => moderate(m.id)}
                        className="shrink-0 text-[10px] opacity-0 transition group-hover:opacity-70 hover:!opacity-100"
                        title="Remove message"
                      >
                        Remove
                      </button>
                    )}
                  </div>
                  <p className="mt-1 text-[10px] opacity-60">
                    {formatRelative(m.created_at)}
                    {isOwn && m.id === lastOwnId && seenByOthers && <span className="ml-2">&middot; Seen</span>}
                  </p>
                </div>
              );
            });
          })()
        )}
        <div ref={bottomRef} />
      </div>

      {typingUsers.size > 0 && <p className="mt-1 text-xs text-fg-subtle">Someone is typing…</p>}

      <div className="mt-4 flex gap-3">
        <input
          className="input"
          placeholder="Type a message…"
          value={input}
          onChange={(e) => { setInput(e.target.value); socketRef.current?.sendTyping(); }}
          onKeyDown={(e) => e.key === "Enter" && send()}
        />
        <button onClick={send} disabled={!input.trim()} className="btn-primary shrink-0">Send</button>
      </div>
    </div>
  );
}
