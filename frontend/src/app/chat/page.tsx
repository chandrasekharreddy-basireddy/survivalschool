"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface RoomOut { id: string; name: string; room_type: string }

export default function ChatRoomsPage() {
  const { user, loading } = useAuth();
  const toast = useToast();
  const [rooms, setRooms] = useState<RoomOut[] | null>(null);
  const [newRoomName, setNewRoomName] = useState("");
  const [creating, setCreating] = useState(false);

  const load = () => {
    apiFetch<RoomOut[]>("/chat/rooms").then(setRooms).catch(() => setRooms([]));
  };

  useEffect(() => {
    if (user) load();
  }, [user]);

  const createRoom = async () => {
    if (!newRoomName.trim()) return;
    setCreating(true);
    try {
      await apiFetch("/chat/rooms", { method: "POST", body: JSON.stringify({ name: newRoomName, room_type: "group" }) });
      setNewRoomName("");
      load();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't create the room.", "error");
    } finally {
      setCreating(false);
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
    <div className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Chat</h1>

      <div className="mt-6 flex gap-3">
        <input className="input" placeholder="New room name" value={newRoomName} onChange={(e) => setNewRoomName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && createRoom()} />
        <button onClick={createRoom} disabled={creating} className="btn-primary shrink-0">Create</button>
      </div>

      {rooms === null ? (
        <p className="mt-8 text-sm text-fg-subtle">Loading…</p>
      ) : rooms.length === 0 ? (
        <div className="mt-8 rounded-lg border border-dashed border-ink-700 p-10 text-center text-sm text-fg-subtle">
          No chat rooms yet. Create one to get started.
        </div>
      ) : (
        <ul className="mt-6 space-y-2">
          {rooms.map((r) => (
            <li key={r.id}>
              <Link href={`/chat/${r.id}`} className="card flex items-center justify-between !p-4 transition hover:border-brand-500/40">
                <span className="font-medium text-fg">{r.name}</span>
                <span className="text-xs uppercase tracking-wide text-fg-subtle">{r.room_type}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
