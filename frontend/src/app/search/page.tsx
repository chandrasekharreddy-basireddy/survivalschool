"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api";

interface SearchResult { type: string; id: string; title: string; snippet: string; course_id: string | null; course_slug: string | null }

function SearchResults() {
  const searchParams = useSearchParams();
  const q = searchParams.get("q") || "";
  const [results, setResults] = useState<SearchResult[] | null>(null);

  useEffect(() => {
    if (q.trim().length < 2) {
      setResults([]);
      return;
    }
    apiFetch<{ results: SearchResult[] }>(`/search?q=${encodeURIComponent(q)}&limit=30`, { auth: false })
      .then((r) => setResults(r.results))
      .catch(() => setResults([]));
  }, [q]);

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Search results</h1>
      <p className="mt-1 text-sm text-fg-muted">{q ? `Showing results for "${q}"` : "Enter a search term."}</p>

      {results === null ? (
        <p className="mt-8 text-sm text-fg-subtle">Searching…</p>
      ) : results.length === 0 ? (
        <div className="card mt-8 text-center text-sm text-fg-muted">No matches found. Try a different search.</div>
      ) : (
        <div className="mt-8 space-y-3">
          {results.map((r) => (
            <Link
              key={`${r.type}-${r.id}`}
              href={r.type === "course" ? `/courses/${r.course_slug}` : `/discussions/${r.id}`}
              className="card block transition hover:border-brand-500/50"
            >
              <span className="badge uppercase">{r.type}</span>
              <h2 className="mt-2 font-semibold text-fg">{r.title}</h2>
              <p className="mt-1 text-sm text-fg-muted">{r.snippet}</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>}>
      <SearchResults />
    </Suspense>
  );
}
