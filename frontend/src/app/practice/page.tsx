"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatDate } from "@/lib/format";
import { PageLoader } from "@/components/PageLoader";

interface Bookmark { id: string; question_id: string; prompt: string; created_at: string }
interface HistoryItem { id: string; source: string; score_percent: number | null; started_at: string; submitted_at: string | null }

const SOURCE_LABEL: Record<string, string> = {
  bookmarks: "Bookmarked questions",
  mistakes: "Questions you've missed",
};

export default function PracticeHomePage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [starting, setStarting] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<Bookmark[]>("/practice/bookmarks").then(setBookmarks).catch(() => setBookmarks([]));
    apiFetch<HistoryItem[]>("/practice/me/sessions").then(setHistory).catch(() => setHistory([]));
  }, [user]);

  const start = async (source: "bookmarks" | "mistakes") => {
    setStarting(source);
    try {
      const session = await apiFetch<{ id: string }>("/practice/sessions", {
        method: "POST",
        body: JSON.stringify({ source, limit: 10 }),
      });
      router.push(`/practice/${session.id}`);
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't start a practice session.", "error");
    } finally {
      setStarting(null);
    }
  };

  if (loading) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted"><PageLoader size="md" /></div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to practice.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Practice</h1>
      <p className="mt-1 text-sm text-fg-muted">
        Untimed and low-stakes — practice sessions show you the right answer immediately and never affect your score, certificate, or points.
      </p>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <div className="card !p-5">
          <h2 className="font-semibold text-fg">Bookmarks</h2>
          <p className="mt-1 text-xs text-fg-muted">{bookmarks.length} question{bookmarks.length === 1 ? "" : "s"} saved</p>
          <button onClick={() => start("bookmarks")} disabled={starting !== null || bookmarks.length === 0} className="btn-primary mt-4 w-full">
            {starting === "bookmarks" ? "Starting…" : "Practice bookmarks"}
          </button>
        </div>
        <div className="card !p-5">
          <h2 className="font-semibold text-fg">Review mistakes</h2>
          <p className="mt-1 text-xs text-fg-muted">Questions you&apos;ve answered wrong in a contest or elimination battle</p>
          <button onClick={() => start("mistakes")} disabled={starting !== null} className="btn-primary mt-4 w-full">
            {starting === "mistakes" ? "Starting…" : "Review mistakes"}
          </button>
        </div>
      </div>

      {bookmarks.length > 0 && (
        <div className="mt-8">
          <h2 className="font-semibold text-fg">Your bookmarks</h2>
          <div className="mt-3 space-y-2">
            {bookmarks.map((b) => (
              <div key={b.id} className="card !p-4 text-sm text-fg-muted">
                <p className="text-fg">{b.prompt}</p>
                <p className="mt-1 text-xs text-fg-subtle">saved {formatDate(b.created_at)}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {history.length > 0 && (
        <div className="mt-8">
          <h2 className="font-semibold text-fg">Recent sessions</h2>
          <ul className="mt-3 divide-y divide-ink-800">
            {history.slice(0, 10).map((h) => (
              <li key={h.id} className="flex items-center justify-between py-2.5 text-sm">
                <span className="text-fg-muted">{SOURCE_LABEL[h.source] || h.source}</span>
                <span className="text-fg-subtle">
                  {h.score_percent != null ? `${h.score_percent}%` : "in progress"} · {formatDate(h.started_at)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
