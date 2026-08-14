"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, getAccessToken } from "@/lib/api";
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
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [input, setInput] = useState("");
  const [typingUsers, setTypingUsers] = useState<Set<string>>(new Set());
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<ChatSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

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
      } else if (evt.event === "chat.typing") {
        setTypingUsers((prev) => new Set(prev).add(evt.user_id));
        setTimeout(() => setTypingUsers((prev) => { const next = new Set(prev); next.delete(evt.user_id); return next; }), 3000);
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

  const send = () => {
    if (!input.trim() || !socketRef.current) return;
    socketRef.current.sendMessage(input);
    setInput("");
  };

  if (loading) return <div className="mx-auto max-w-2xl px-6 py-16 text-slate-400">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-slate-300">Sign in to use chat.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-4.5rem)] max-w-2xl flex-col px-6 py-6">
      <div className="flex items-center justify-between">
        <Link href="/chat" className="text-sm text-slate-400 hover:text-white">&larr; All rooms</Link>
        <span className={`text-xs ${connected ? "text-emerald-400" : "text-slate-500"}`}>{connected ? "Live" : "Connecting…"}</span>
      </div>

      <div className="card mt-4 flex-1 space-y-3 overflow-y-auto">
        {messages.length === 0 ? (
          <p className="text-sm text-slate-500">No messages yet — say hello.</p>
        ) : (
          messages.filter((m) => !m.is_deleted).map((m) => (
            <div key={m.id} className={`max-w-[75%] rounded-lg px-4 py-2 text-sm ${m.sender_id === user.id ? "ml-auto bg-brand-500 text-white" : "bg-ink-800 text-slate-200"}`}>
              <p>{m.body}</p>
              <p className="mt-1 text-[10px] opacity-60">{formatRelative(m.created_at)}</p>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {typingUsers.size > 0 && <p className="mt-1 text-xs text-slate-500">Someone is typing…</p>}

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
