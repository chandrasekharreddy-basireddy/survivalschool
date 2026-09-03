"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { ContestCountdown } from "@/components/ContestCountdown";
import { PageLoader } from "@/components/PageLoader";

interface Contest {
  id: string;
  title: string;
  description: string;
  contest_type: string;
  is_auto_generated: boolean;
  starts_at: string;
  ends_at: string;
  duration_seconds: number;
  top_n_awarded: number;
  status: string;
  question_count: number;
}

const STATUS_LABEL: Record<string, string> = { scheduled: "Upcoming", open: "Open now", closed: "Finished" };
const STATUS_STYLE: Record<string, string> = {
  scheduled: "border-brand-500/40 text-brand-600 dark:text-brand-400",
  open: "border-emerald-500/40 text-emerald-700 dark:text-emerald-400",
  closed: "border-ink-700 text-fg-subtle",
};

const PAGE_SIZE = 50;

export default function ContestsPage() {
  const [upcoming, setUpcoming] = useState<Contest[] | null>(null);
  const [all, setAll] = useState<Contest[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    apiFetch<Contest[]>("/contests/upcoming", { auth: false }).then(setUpcoming).catch(() => setUpcoming([]));
    apiFetch<Contest[]>(`/contests?limit=${PAGE_SIZE}&offset=0`, { auth: false })
      .then((page) => {
        setAll(page);
        setHasMore(page.length === PAGE_SIZE);
      })
      .catch(() => setAll([]));
  }, []);

  const loadMore = async () => {
    if (!all || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await apiFetch<Contest[]>(`/contests?limit=${PAGE_SIZE}&offset=${all.length}`, { auth: false });
      setAll((prev) => [...(prev ?? []), ...page]);
      setHasMore(page.length === PAGE_SIZE);
    } catch {
      // leave the "load more" control in place so the user can retry
    } finally {
      setLoadingMore(false);
    }
  };

  const next = upcoming?.[0];

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-fg">Contests</h1>
          <p className="mt-1 text-sm text-fg-muted">
            Live, time-boxed competitions from the shared question bank, one attempt each. The top finishers win a real certificate.
          </p>
        </div>
        <Link href="/contests/ai-weekly/register" className="btn-secondary shrink-0">Register: AI Weekly Exam</Link>
      </div>

      {next && (
        <div className="card mt-6 border-brand-500/40 bg-brand-500/5">
          <p className="text-xs uppercase tracking-widest text-brand-600 dark:text-brand-400">Next up</p>
          <h2 className="mt-1 text-lg font-semibold text-fg">{next.title}</h2>
          <p className="mt-1 text-sm text-fg-muted">{next.description}</p>
          <div className="mt-4 flex flex-wrap items-center gap-4">
            <ContestCountdown startsAt={next.starts_at} endsAt={next.ends_at} status={next.status} />
            <Link href={`/contests/${next.id}`} className="btn-primary">View contest</Link>
          </div>
        </div>
      )}

      <div className="mt-8 space-y-3">
        <h2 className="font-semibold text-fg">All contests</h2>
        {all === null && <p className="text-sm text-fg-subtle"><PageLoader size="sm" /></p>}
        {all !== null && all.length === 0 && <p className="text-sm text-fg-subtle">No contests yet — check back this weekend.</p>}
        {all?.map((c) => (
          <Link key={c.id} href={`/contests/${c.id}`} className="card !p-4 flex items-center justify-between gap-4 transition hover:border-brand-500/50">
            <div className="min-w-0">
              <p className="truncate font-medium text-fg">{c.title}</p>
              <p className="text-xs text-fg-subtle">
                {formatDateTime(c.starts_at)} · {c.question_count} questions · top {c.top_n_awarded} win a certificate
              </p>
            </div>
            <span className={`shrink-0 rounded-full border px-2.5 py-1 text-xs font-medium ${STATUS_STYLE[c.status] || ""}`}>
              {STATUS_LABEL[c.status] || c.status}
            </span>
          </Link>
        ))}
        {hasMore && (
          <button
            type="button"
            onClick={loadMore}
            disabled={loadingMore}
            className="btn-secondary w-full disabled:opacity-60"
          >
            {loadingMore ? "Loading…" : "Load more"}
          </button>
        )}
      </div>
    </div>
  );
}
