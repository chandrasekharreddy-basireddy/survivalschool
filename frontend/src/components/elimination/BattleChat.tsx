"use client";

import { useEffect, useRef, useState } from "react";
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

/**
 * Compact live chat panel embedded in the elimination battle page — reuses
 * the same /ws/chat/{room_id} socket and REST history endpoint the
 * standalone chat inbox uses (app/chat/[roomId]/page.tsx), so messages sent
 * here show up there too and vice versa. Every elimination battle gets its
 * own chat room (created in elimination_service.py's create_battle) with
 * every participant added as a member as they join, so this never needs its
 * own membership/permission logic — it's just a differently-shaped view
 * onto the same room.
 */
export function BattleChat({ roomId }: { roomId: string }) {
  const { user } = useAuth();
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<ChatSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<MessageOut[]>(`/chat/rooms/${roomId}/messages?limit=100`).then(setMessages).catch(() => setMessages([]));

    const token = getAccessToken();
    if (!token) return;
    const socket = new ChatSocket(roomId, token);
    socketRef.current = socket;
    const unsubState = socket.onStateChange(setConnected);
    socket.connect();

    const unsubscribe = socket.on((evt: ChatEvent) => {
      if (evt.event === "chat.message" && evt.room_id === roomId) {
        setMessages((prev) => [...prev, { id: evt.id, room_id: evt.room_id, sender_id: evt.sender_id, body: evt.body, created_at: evt.created_at, is_deleted: false }]);
      }
    });

    return () => {
      unsubscribe();
      unsubState();
      socket.close();
      setConnected(false);
    };
  }, [user, roomId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = () => {
    if (!input.trim() || !socketRef.current) return;
    socketRef.current.sendMessage(input);
    setInput("");
  };

  if (!user) return null;

  const visible = messages.filter((m) => !m.is_deleted);

  return (
    <div className="card flex flex-col">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-fg">Battle chat</h2>
        <span className={`text-xs ${connected ? "text-emerald-700 dark:text-emerald-400" : "text-fg-subtle"}`}>
          {connected ? "Live" : "Connecting…"}
        </span>
      </div>

      <div className="mt-3 max-h-64 flex-1 space-y-1.5 overflow-y-auto">
        {visible.length === 0 ? (
          <p className="py-4 text-center text-xs text-fg-subtle">No messages yet — say hello.</p>
        ) : (
          visible.map((m) => {
            const isOwn = m.sender_id === user.id;
            return (
              <div key={m.id} className={`flex ${isOwn ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] rounded-xl px-3 py-1.5 text-sm leading-snug ${isOwn ? "bg-brand-600 text-white" : "bg-ink-800 text-fg"}`}>
                  <p className="whitespace-pre-wrap break-words">{m.body}</p>
                  <p className={`mt-0.5 text-[10px] ${isOwn ? "text-white/70" : "text-fg-subtle"}`}>{formatRelative(m.created_at)}</p>
                </div>
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>

      <div className="mt-3 flex items-center gap-2">
        <input
          className="input flex-1 !py-1.5 text-sm"
          placeholder="Message…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              send();
            }
          }}
        />
        <button onClick={send} disabled={!input.trim()} className="btn-secondary !px-3 !py-1.5 text-xs">
          Send
        </button>
      </div>
    </div>
  );
}
