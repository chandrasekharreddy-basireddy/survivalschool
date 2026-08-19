"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

interface SearchResult {
  type: "course" | "discussion";
  id: string;
  title: string;
  snippet: string;
  course_id: string | null;
  course_slug: string | null;
}

/** Debounced global search — GET /search, public (no auth required), only
 * ever surfaces published-course content (enforced server-side, see
 * app/api/v1/search.py). Navigates to the course page or, for a discussion
 * hit, straight to that course's discussion thread. */
export function SearchBar() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const q = query.trim();
    if (q.length < 2) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const resp = await apiFetch<{ results: SearchResult[] }>(`/search?q=${encodeURIComponent(q)}&limit=8`, { auth: false });
        setResults(resp.results);
        setOpen(true);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  const goTo = (r: SearchResult) => {
    setOpen(false);
    setQuery("");
    if (r.type === "course" && r.course_slug) router.push(`/courses/${r.course_slug}`);
    else if (r.type === "discussion") router.push(`/discussions/${r.id}`);
  };

  return (
    <div ref={containerRef} className="relative w-full">
      <div className="relative">
        <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-subtle" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder="Search courses, discussions…"
          aria-label="Search"
          className="input !py-2 pl-9 text-sm"
        />
      </div>
      {open && (query.trim().length >= 2) && (
        <div className="absolute left-0 right-0 top-full z-50 mt-2 max-h-80 overflow-y-auto rounded-lg border border-ink-700 bg-ink-900 shadow-lg">
          {loading && <p className="px-4 py-3 text-sm text-fg-subtle">Searching…</p>}
          {!loading && results.length === 0 && <p className="px-4 py-3 text-sm text-fg-subtle">No matches for &ldquo;{query}&rdquo;.</p>}
          {!loading &&
            results.map((r) => (
              <button
                key={`${r.type}-${r.id}`}
                onClick={() => goTo(r)}
                className="flex w-full flex-col items-start gap-0.5 border-b border-ink-800 px-4 py-2.5 text-left last:border-0 hover:bg-ink-800"
              >
                <span className="flex items-center gap-2 text-sm font-medium text-fg">
                  <span className="badge !py-0.5 !text-[10px] uppercase">{r.type}</span>
                  {r.title}
                </span>
                {r.snippet && <span className="line-clamp-1 text-xs text-fg-subtle">{r.snippet}</span>}
              </button>
            ))}
        </div>
      )}
    </div>
  );
}

function SearchIcon({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={className}>
      <circle cx="11" cy="11" r="7" />
      <path strokeLinecap="round" d="m21 21-4.35-4.35" />
    </svg>
  );
}
