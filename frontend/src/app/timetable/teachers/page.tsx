"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";
import { PageLoader } from "@/components/PageLoader";

const WEEKDAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
// Sun/Sat tabs are only shown if a teacher actually has a class that day —
// most institutions run Mon-Fri, but nothing here assumes that.
const WEEKDAY_ORDER = [1, 2, 3, 4, 5, 6, 0];

interface TeacherSummary { teacher_name: string; class_count: number; day_count: number }
interface Entry {
  id: string; course_name: string; course_code: string | null; class_date: string;
  day_of_week: number; start_time: string; end_time: string; room: string | null; section: string;
}

function fmtTime(t: string): string {
  const [h, m] = t.split(":");
  const hour = parseInt(h, 10);
  const period = hour >= 12 ? "PM" : "AM";
  const displayHour = hour % 12 === 0 ? 12 : hour % 12;
  return `${displayHour}:${m} ${period}`;
}

function toMinutes(t: string): number {
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
}

function todayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// Derived from the date string itself (JS Date's own 0=Sunday..6=Saturday
// convention, matching WEEKDAY_NAMES/WEEKDAY_ORDER above) rather than
// trusting the backend's day_of_week field, which is Python's
// date.weekday() convention (0=Monday..6=Sunday) — mixing the two silently
// mislabels every entry by a day.
function weekdayOf(dateStr: string): number {
  return new Date(dateStr + "T00:00:00").getDay();
}

export default function TeacherTimetablePage() {
  const { user, loading } = useAuth();

  const [teachers, setTeachers] = useState<TeacherSummary[] | null>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [loadingEntries, setLoadingEntries] = useState(false);
  const [activeDay, setActiveDay] = useState<number | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<TeacherSummary[]>("/timetable/campus/teachers").then(setTeachers).catch(() => setTeachers([]));
  }, [user]);

  useEffect(() => {
    if (!selected) { setEntries(null); return; }
    setLoadingEntries(true);
    const today = todayStr();
    const weekOut = new Date();
    weekOut.setDate(weekOut.getDate() + 6);
    const dateTo = `${weekOut.getFullYear()}-${String(weekOut.getMonth() + 1).padStart(2, "0")}-${String(weekOut.getDate()).padStart(2, "0")}`;
    apiFetch<Entry[]>(`/timetable/campus?teacher=${encodeURIComponent(selected)}&date_from=${today}&date_to=${dateTo}`)
      .then((rows) => {
        setEntries(rows);
        const days = [...new Set(rows.map((r) => weekdayOf(r.class_date)))];
        setActiveDay(days.length > 0 ? WEEKDAY_ORDER.find((d) => days.includes(d)) ?? days[0] : null);
      })
      .catch(() => setEntries([]))
      .finally(() => setLoadingEntries(false));
  }, [selected]);

  const filteredTeachers = useMemo(() => {
    if (!teachers) return [];
    const q = query.trim().toLowerCase();
    return q ? teachers.filter((t) => t.teacher_name.toLowerCase().includes(q)) : teachers;
  }, [teachers, query]);

  const selectedSummary = teachers?.find((t) => t.teacher_name === selected) ?? null;
  const availableDays = useMemo(
    () => WEEKDAY_ORDER.filter((d) => (entries || []).some((e) => weekdayOf(e.class_date) === d)),
    [entries]
  );
  const dayEntries = (entries || [])
    .filter((e) => weekdayOf(e.class_date) === activeDay)
    .slice()
    .sort((a, b) => a.start_time.localeCompare(b.start_time));

  if (loading) return <div className="mx-auto max-w-5xl px-6 py-16 text-fg-muted"><PageLoader size="md" /></div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to look up a teacher&apos;s timetable.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Teacher timetable</h1>
      <p className="mt-1 text-sm text-fg-muted">Look up any teacher&apos;s weekly class schedule from the synced campus timetable.</p>

      <div className="card mt-6 !p-4">
        <div className="flex items-center justify-between gap-3">
          <input
            type="text" value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a teacher name…" className="input flex-1"
          />
          {teachers && <span className="shrink-0 text-xs text-fg-subtle">{teachers.length} teacher{teachers.length === 1 ? "" : "s"}</span>}
        </div>

        {teachers === null ? (
          <div className="mt-4"><PageLoader size="sm" /></div>
        ) : filteredTeachers.length === 0 ? (
          <p className="mt-4 text-sm text-fg-muted">
            {teachers.length === 0 ? "No teacher has a class scheduled in the next 7 days." : "No teacher matches that search."}
          </p>
        ) : (
          <div className="mt-3 max-h-64 overflow-y-auto rounded-lg border border-ink-800">
            {filteredTeachers.map((t) => (
              <button
                key={t.teacher_name}
                onClick={() => setSelected(t.teacher_name)}
                className={`flex w-full items-center justify-between border-b border-ink-800 px-3 py-2 text-left text-sm last:border-b-0 transition ${
                  selected === t.teacher_name ? "bg-brand-500/10 text-brand-600 dark:text-brand-400" : "text-fg hover:bg-ink-900"
                }`}
              >
                <span className="font-medium">{t.teacher_name}</span>
                <span className="text-xs text-fg-subtle">{t.class_count}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {selectedSummary && (
        <div className="mt-6">
          <h2 className="text-xl font-bold text-fg">{selectedSummary.teacher_name}</h2>
          <p className="mt-0.5 text-sm text-fg-muted">
            {selectedSummary.class_count} weekly class{selectedSummary.class_count === 1 ? "" : "es"} on {selectedSummary.day_count} day{selectedSummary.day_count === 1 ? "" : "s"}
          </p>

          {loadingEntries ? (
            <div className="mt-6"><PageLoader size="sm" /></div>
          ) : (
            <>
              {availableDays.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {availableDays.map((d) => (
                    <button
                      key={d}
                      onClick={() => setActiveDay(d)}
                      className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                        activeDay === d ? "bg-brand-500 text-white" : "bg-ink-900 text-fg-subtle hover:text-fg"
                      }`}
                    >
                      {WEEKDAY_NAMES[d]}
                    </button>
                  ))}
                </div>
              )}

              <div className="card mt-4 !p-4">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-fg">
                    {selectedSummary.teacher_name} — {activeDay !== null ? WEEKDAY_NAMES[activeDay] : ""}
                  </p>
                  <span className="text-xs text-fg-subtle">{dayEntries.length} class{dayEntries.length === 1 ? "" : "es"}</span>
                </div>
                {dayEntries.length === 0 ? (
                  <p className="mt-3 text-sm text-fg-muted">No classes that day.</p>
                ) : (
                  <div className="mt-3 space-y-2">
                    {dayEntries.map((e) => (
                      <div key={e.id} className="rounded-lg border border-ink-700 bg-ink-950 p-3">
                        <p className="text-sm font-medium text-fg">
                          {e.course_name} {e.course_code && <span className="text-fg-subtle">({e.course_code})</span>}
                        </p>
                        <p className="mt-1 text-xs text-fg-muted">{e.room || "TBD"} · Section {e.section}</p>
                        <p className="mt-1 text-xs text-fg-subtle">
                          {fmtTime(e.start_time)} – {fmtTime(e.end_time)} · {toMinutes(e.end_time) - toMinutes(e.start_time)}m
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
