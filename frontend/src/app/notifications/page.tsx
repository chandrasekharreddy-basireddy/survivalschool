"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";
import { formatRelative } from "@/lib/format";

interface NotificationOut {
  id: string;
  category: string;
  title: string;
  body: string;
  link_url: string | null;
  read_at: string | null;
  created_at: string;
}

export default function NotificationsPage() {
  const { user, loading } = useAuth();
  const [items, setItems] = useState<NotificationOut[] | null>(null);
  const [filter, setFilter] = useState<"all" | "unread">("all");

  const load = () => {
    apiFetch<NotificationOut[]>(`/notifications?limit=50${filter === "unread" ? "&unread_only=true" : ""}`)
      .then(setItems)
      .catch(() => setItems([]));
  };

  useEffect(() => {
    if (user) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, filter]);

  const markRead = async (id: string) => {
    setItems((prev) => prev && prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n)));
    try {
      await apiFetch(`/notifications/${id}/read`, { method: "POST" });
    } catch {
      load();
    }
  };

  if (loading) return <div className="mx-auto max-w-2xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to see your notifications.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-fg">Notifications</h1>
        <Link href="/settings" className="text-sm text-brand-400 hover:underline">Preferences</Link>
      </div>

      <div className="mt-4 flex gap-2">
        {(["all", "unread"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-full px-3 py-1 text-xs font-medium ${filter === f ? "bg-brand-500 text-white" : "bg-ink-800 text-fg-muted"}`}
          >
            {f === "all" ? "All" : "Unread"}
          </button>
        ))}
      </div>

      {items === null ? (
        <p className="mt-8 text-sm text-fg-subtle">Loading…</p>
      ) : items.length === 0 ? (
        <div className="mt-8 rounded-lg border border-dashed border-ink-700 p-10 text-center text-sm text-fg-subtle">
          You&apos;re all caught up.
        </div>
      ) : (
        <ul className="mt-6 space-y-2">
          {items.map((n) => {
            const content = (
              <div
                className={`card cursor-pointer transition ${n.read_at ? "opacity-60" : "border-brand-500/40"}`}
                onClick={() => !n.read_at && markRead(n.id)}
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm font-medium text-fg">{n.title}</p>
                  {!n.read_at && <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-brand-500" />}
                </div>
                <p className="mt-1 text-xs text-fg-subtle">{n.body}</p>
                <p className="mt-2 text-[11px] text-fg-subtle">{formatRelative(n.created_at)}</p>
              </div>
            );
            return (
              <li key={n.id}>
                {n.link_url ? <Link href={n.link_url}>{content}</Link> : content}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
