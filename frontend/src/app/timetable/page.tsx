"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";

interface CampusEntry {
  id: string;
  section: string;
  course_name: string;
  course_code: string | null;
  class_date: string;
  start_time: string;
  end_time: string;
  room: string | null;
  teacher_name: string | null;
  is_elective: boolean;
  is_cancelled: boolean;
}

function fmtTime(t: string): string {
  const [h, m] = t.split(":");
  const hour = parseInt(h, 10);
  const period = hour >= 12 ? "PM" : "AM";
  const displayHour = hour % 12 === 0 ? 12 : hour % 12;
  return `${displayHour}:${m} ${period}`;
}

function fmtDate(d: string): string {
  return new Date(d + "T00:00:00").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

export default function TimetablePage() {
  const { user, loading } = useAuth();
  const [entries, setEntries] = useState<CampusEntry[] | null>(null);
  const [needsSection, setNeedsSection] = useState(false);

  useEffect(() => {
    if (!user) return;
    apiFetch<CampusEntry[]>("/timetable/campus/me")
      .then(setEntries)
      .catch((err) => {
        if (err instanceof ApiError && err.code === "validation_error") setNeedsSection(true);
        setEntries([]);
      });
  }, [user]);

  if (loading) return <div className="mx-auto max-w-5xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to see your timetable.</p>
      </div>
    );
  }

  const byDate = new Map<string, CampusEntry[]>();
  for (const e of entries || []) {
    if (!byDate.has(e.class_date)) byDate.set(e.class_date, []);
    byDate.get(e.class_date)!.push(e);
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Your timetable</h1>
      <p className="mt-1 text-sm text-fg-muted">Your university&apos;s class schedule for your section, kept in sync by your institution.</p>

      {needsSection && (
        <div className="card mt-8 !p-4 text-sm text-fg-muted">
          Set your section in your <a href="/profile" className="font-medium text-brand-600 underline dark:text-brand-400">profile</a> to
          see your campus timetable here.
        </div>
      )}

      {entries !== null && !needsSection && entries.length === 0 && (
        <div className="card mt-8 text-center text-sm text-fg-muted">No classes scheduled yet for your section.</div>
      )}

      {entries !== null && entries.length > 0 && (
        <div className="mt-8 space-y-3">
          {[...byDate.entries()].map(([date, dayEntries]) => (
            <div key={date} className="card !p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">{fmtDate(date)}</p>
              <div className="mt-2 space-y-2">
                {dayEntries
                  .slice()
                  .sort((a, b) => a.start_time.localeCompare(b.start_time))
                  .map((e) => (
                    <div key={e.id} className={`rounded-lg border p-3 ${e.is_cancelled ? "border-red-500/30 bg-red-500/5" : "border-ink-700 bg-ink-950"}`}>
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-fg">
                          {e.course_name} {e.course_code && <span className="text-fg-subtle">({e.course_code})</span>}
                        </p>
                        {e.is_cancelled && <span className="text-xs font-semibold text-red-700 dark:text-red-400">Cancelled</span>}
                      </div>
                      <p className="mt-1 text-xs text-fg-muted">{fmtTime(e.start_time)} – {fmtTime(e.end_time)}</p>
                      <p className="mt-1 text-xs text-fg-subtle">
                        {e.room || "TBD"}{e.teacher_name ? ` · ${e.teacher_name}` : ""}{e.is_elective ? " · Elective" : ""}
                      </p>
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
