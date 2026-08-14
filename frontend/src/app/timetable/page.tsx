"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, getAccessToken } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

interface TimetableEntry {
  id: string;
  course_id: string;
  course_title: string;
  instructor_name: string | null;
  term: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  room: string;
  session_type: string;
}

function fmtTime(t: string): string {
  const [h, m] = t.split(":");
  const hour = parseInt(h, 10);
  const period = hour >= 12 ? "PM" : "AM";
  const displayHour = hour % 12 === 0 ? 12 : hour % 12;
  return `${displayHour}:${m} ${period}`;
}

export default function TimetablePage() {
  const { user, loading } = useAuth();
  const [entries, setEntries] = useState<TimetableEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<TimetableEntry[]>("/timetable/me")
      .then(setEntries)
      .catch(() => setError("Couldn't load your timetable."));
  }, [user]);

  if (loading) return <div className="mx-auto max-w-5xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to see your timetable.</p>
      </div>
    );
  }

  const byDay: TimetableEntry[][] = DAYS.map((_, i) => (entries || []).filter((e) => e.day_of_week === i));

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-fg">Your timetable</h1>
          <p className="mt-1 text-sm text-fg-muted">Built from your course enrollments — updates automatically when an instructor changes a schedule.</p>
        </div>
        <DownloadIcsButton />
      </div>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      {entries !== null && entries.length === 0 && (
        <div className="card mt-8 text-center text-sm text-fg-muted">
          No scheduled classes yet — enroll in a course with a published timetable, or check back once your instructor sets one up.
        </div>
      )}

      <div className="mt-8 grid gap-4 lg:grid-cols-7">
        {DAYS.map((day, i) => (
          <div key={day} className="card !p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">{day}</p>
            <div className="mt-3 space-y-2">
              {byDay[i].length === 0 && <p className="text-xs text-fg-subtle">—</p>}
              {byDay[i]
                .slice()
                .sort((a, b) => a.start_time.localeCompare(b.start_time))
                .map((e) => (
                  <div key={e.id} className="rounded-lg border border-ink-700 bg-ink-950 p-3">
                    <p className="text-sm font-medium text-fg">{e.course_title}</p>
                    <p className="mt-1 text-xs text-fg-muted">{fmtTime(e.start_time)} – {fmtTime(e.end_time)}</p>
                    <p className="mt-1 text-xs text-fg-subtle">
                      {e.room || "TBD"} · <span className="capitalize">{e.session_type}</span>
                    </p>
                  </div>
                ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function DownloadIcsButton() {
  const [downloading, setDownloading] = useState(false);

  const download = async () => {
    setDownloading(true);
    try {
      const token = getAccessToken();
      const resp = await fetch(`${API_BASE}/timetable/me/export.ics`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!resp.ok) throw new Error("Export failed");
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "timetable.ics";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      /* toast intentionally omitted here — the button itself gives instant visual feedback */
    } finally {
      setDownloading(false);
    }
  };

  return (
    <button onClick={download} disabled={downloading} className="btn-secondary">
      {downloading ? "Preparing…" : "Add to calendar (.ics)"}
    </button>
  );
}
