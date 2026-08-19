"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";
import { initials } from "@/lib/avatar";

export interface RoomOut {
  id: string;
  name: string;
  room_type: string;
  other_user_id: string | null;
  other_user_name: string | null;
}

// The layout owns the one /chat/rooms fetch for the whole /chat/* subtree;
// child pages (e.g. the room page) read from this instead of independently
// re-fetching the full list just to find their own room in it — that used
// to double both the request count and the backend work on every room visit.
const ChatRoomsContext = createContext<RoomOut[] | null>(null);

export function useChatRooms(): RoomOut[] | null {
  return useContext(ChatRoomsContext);
}

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const [rooms, setRooms] = useState<RoomOut[] | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<RoomOut[]>("/chat/rooms").then(setRooms).catch(() => setRooms([]));
  }, [user]);

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
    <div className="mx-auto flex h-[calc(100vh-3.5rem)] max-w-6xl">
      <aside className="hidden w-72 shrink-0 flex-col border-r border-ink-800 sm:flex">
        <div className="flex items-center justify-between px-4 py-4">
          <h1 className="text-sm font-semibold text-fg">Messages</h1>
          <Link href="/follows" className="text-xs font-medium text-brand-600 hover:underline dark:text-brand-400">
            New
          </Link>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-4">
          {rooms === null && <p className="px-2 py-4 text-xs text-fg-subtle">Loading…</p>}
          {rooms !== null && rooms.length === 0 && (
            <div className="px-2 py-6 text-center text-xs text-fg-subtle">
              No conversations yet.
              <br />
              <Link href="/follows" className="mt-2 inline-block font-medium text-brand-600 hover:underline dark:text-brand-400">
                Find people to message
              </Link>
            </div>
          )}
          {rooms?.map((r) => {
            const label = r.room_type === "direct" ? r.other_user_name || r.name : r.name;
            const active = pathname === `/chat/${r.id}`;
            return (
              <Link
                key={r.id}
                href={`/chat/${r.id}`}
                className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                  active ? "bg-ink-800 text-fg" : "text-fg-muted hover:bg-ink-900 hover:text-fg"
                }`}
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-800 text-xs font-semibold text-fg-muted">
                  {initials(label)}
                </span>
                <span className="min-w-0 flex-1 truncate">{label}</span>
                {r.room_type !== "direct" && (
                  <span className="shrink-0 text-[10px] uppercase tracking-wide text-fg-subtle">{r.room_type}</span>
                )}
              </Link>
            );
          })}
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <ChatRoomsContext.Provider value={rooms}>{children}</ChatRoomsContext.Provider>
      </div>
    </div>
  );
}
