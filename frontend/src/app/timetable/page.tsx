"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

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

interface PersonalEntry {
  id: string;
  course_name: string;
  course_code: string | null;
  class_date: string;
  start_time: string;
  end_time: string;
  room: string | null;
  teacher_name: string | null;
  is_elective: boolean;
}

// A single shape the calendar/highlight rendering below works from,
// regardless of which source (campus or a personal upload) it came from.
interface DisplayEntry {
  id: string;
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

interface CampusSection {
  school: string | null;
  year_of_study: string | null;
  section: string;
  lab_groups: string[];
}

interface Profile {
  school: string | null;
  section: string | null;
}

interface UploadResult { total_rows: number; imported: number; error_rows: { row_number: number; error: string }[] }

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

function todayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function toMinutes(t: string): number {
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
}

export default function TimetablePage() {
  const { user, loading } = useAuth();
  const toast = useToast();

  const [personalEntries, setPersonalEntries] = useState<PersonalEntry[] | null>(null);
  const [campusEntries, setCampusEntries] = useState<CampusEntry[] | null>(null);
  const [needsSection, setNeedsSection] = useState(false);
  const [sections, setSections] = useState<CampusSection[] | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [pickedKey, setPickedKey] = useState("");
  const [saving, setSaving] = useState(false);

  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [clearing, setClearing] = useState(false);

  const [now, setNow] = useState(() => new Date());

  const loadPersonal = () => apiFetch<PersonalEntry[]>("/timetable/me/personal").then(setPersonalEntries).catch(() => setPersonalEntries([]));
  const loadCampus = () => {
    apiFetch<CampusEntry[]>("/timetable/campus/me")
      .then((rows) => { setCampusEntries(rows); setNeedsSection(false); })
      .catch((err) => {
        if (err instanceof ApiError && err.code === "validation_error") setNeedsSection(true);
        setCampusEntries([]);
      });
  };

  useEffect(() => {
    if (!user) return;
    loadPersonal();
    loadCampus();
    apiFetch<CampusSection[]>("/timetable/campus/sections").then(setSections).catch(() => setSections([]));
    apiFetch<Profile>("/users/me/profile").then((p) => {
      setProfile(p);
      if (p.section) setPickedKey(`${p.school ?? ""} ${p.section}`);
    }).catch(() => setProfile(null));
  }, [user]);

  // Live "what's happening right now" — the reference-repo behavior this
  // page is modeled on (y-bow/SaiU-Timetable). Ticks every 30s; that's
  // plenty for a countdown display, no need for anything tighter.
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);

  const usingPersonal = (personalEntries?.length ?? 0) > 0;
  const entries: DisplayEntry[] = usingPersonal
    ? personalEntries!.map((e) => ({ ...e, is_cancelled: false }))
    : (campusEntries || []);

  const sectionOptions = useMemo(() => {
    return (sections || []).map((s) => ({
      key: `${s.school ?? ""} ${s.section}`,
      school: s.school,
      section: s.section,
      yearOfStudy: s.year_of_study,
      label: [s.school, s.year_of_study ? `Year ${s.year_of_study}` : null, `Section ${s.section}`].filter(Boolean).join(" · "),
    }));
  }, [sections]);

  const saveSection = async () => {
    const picked = sectionOptions.find((o) => o.key === pickedKey);
    if (!picked) return;
    setSaving(true);
    try {
      await apiFetch("/users/me/profile", { method: "PATCH", body: JSON.stringify({ school: picked.school, section: picked.section }) });
      setProfile({ school: picked.school, section: picked.section });
      toast.show("Section saved.", "success");
      loadCampus();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't save your section.", "error");
    } finally {
      setSaving(false);
    }
  };

  const uploadFile = async (file: File) => {
    setUploading(true);
    setUploadResult(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const result = await apiFetch<UploadResult>("/timetable/me/upload", { method: "POST", body });
      setUploadResult(result);
      if (result.error_rows.length === 0) {
        toast.show(`Imported ${result.imported} class${result.imported === 1 ? "" : "es"} from your file.`, "success");
        loadPersonal();
      }
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't read that file.", "error");
    } finally {
      setUploading(false);
    }
  };

  const clearUpload = async () => {
    setClearing(true);
    try {
      await apiFetch("/timetable/me/personal", { method: "DELETE" });
      setPersonalEntries([]);
      setUploadResult(null);
      toast.show("Your uploaded timetable was cleared.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't clear your upload.", "error");
    } finally {
      setClearing(false);
    }
  };

  if (loading) return <div className="mx-auto max-w-5xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to see your timetable.</p>
      </div>
    );
  }

  const byDate = new Map<string, DisplayEntry[]>();
  for (const e of entries) {
    if (!byDate.has(e.class_date)) byDate.set(e.class_date, []);
    byDate.get(e.class_date)!.push(e);
  }

  const currentLabel = profile?.section
    ? sectionOptions.find((o) => o.school === profile.school && o.section === profile.section)?.label
      ?? [profile.school, `Section ${profile.section}`].filter(Boolean).join(" · ")
    : null;

  // Right-now highlight: today's classes only, split into "happening now"
  // (with a progress bar) or "coming up next" (with a countdown).
  const todaysNowMinutes = now.getHours() * 60 + now.getMinutes();
  const todaysEntries = (byDate.get(todayStr()) || []).filter((e) => !e.is_cancelled).slice().sort((a, b) => a.start_time.localeCompare(b.start_time));
  const liveNow = todaysEntries.find((e) => toMinutes(e.start_time) <= todaysNowMinutes && todaysNowMinutes < toMinutes(e.end_time));
  const liveNext = !liveNow ? todaysEntries.find((e) => toMinutes(e.start_time) > todaysNowMinutes) : undefined;
  const liveProgress = liveNow ? Math.min(100, Math.max(0, ((todaysNowMinutes - toMinutes(liveNow.start_time)) / (toMinutes(liveNow.end_time) - toMinutes(liveNow.start_time))) * 100)) : 0;
  const minutesUntilNext = liveNext ? toMinutes(liveNext.start_time) - todaysNowMinutes : 0;

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Your timetable</h1>
      <p className="mt-1 text-sm text-fg-muted">
        {usingPersonal ? "Your own uploaded schedule." : "Your university's class schedule for your section, kept in sync by your institution."}
      </p>

      {(liveNow || liveNext) && (
        <div className="card mt-6 border-brand-500/40">
          {liveNow ? (
            <>
              <p className="text-xs font-semibold uppercase tracking-wide text-brand-600 dark:text-brand-400">Happening now</p>
              <p className="mt-1 text-lg font-semibold text-fg">{liveNow.course_name}</p>
              <p className="mt-0.5 text-sm text-fg-muted">
                {fmtTime(liveNow.start_time)} – {fmtTime(liveNow.end_time)} · {liveNow.room || "TBD"}{liveNow.teacher_name ? ` · ${liveNow.teacher_name}` : ""}
              </p>
              <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-ink-800">
                <div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${liveProgress}%` }} />
              </div>
            </>
          ) : liveNext ? (
            <>
              <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">Up next, in {minutesUntilNext < 60 ? `${minutesUntilNext} min` : `${Math.floor(minutesUntilNext / 60)}h ${minutesUntilNext % 60}m`}</p>
              <p className="mt-1 text-lg font-semibold text-fg">{liveNext.course_name}</p>
              <p className="mt-0.5 text-sm text-fg-muted">
                {fmtTime(liveNext.start_time)} – {fmtTime(liveNext.end_time)} · {liveNext.room || "TBD"}{liveNext.teacher_name ? ` · ${liveNext.teacher_name}` : ""}
              </p>
            </>
          ) : null}
        </div>
      )}

      <div className="card mt-6 !p-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-fg">Upload your own schedule</p>
          {usingPersonal && (
            <button onClick={clearUpload} disabled={clearing} className="text-xs text-fg-subtle underline hover:text-fg">
              {clearing ? "Clearing…" : "Clear & use campus schedule"}
            </button>
          )}
        </div>
        <p className="mt-1 text-xs text-fg-muted">
          CSV or XLSX with columns Course, Date, StartTime, EndTime (Room/Teacher/Elective optional) — it&apos;s parsed
          automatically into the calendar below, replacing any file you uploaded before. This is just your own copy;
          it never touches the shared campus feed.
        </p>
        <label
          htmlFor="personal-timetable-file"
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const dropped = e.dataTransfer.files?.[0];
            if (dropped) uploadFile(dropped);
          }}
          className={`mt-3 flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed px-4 py-6 text-center transition ${
            dragging ? "border-brand-500 bg-brand-500/5" : "border-ink-700 hover:border-ink-600"
          }`}
        >
          <input
            id="personal-timetable-file" type="file" accept=".csv,.xlsx" className="sr-only"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadFile(f); e.target.value = ""; }}
          />
          <p className="text-sm font-medium text-fg">{uploading ? "Uploading…" : "Drag & drop a CSV or XLSX file here"}</p>
          <p className="text-xs text-fg-subtle">or click to browse</p>
        </label>
        {uploadResult && uploadResult.error_rows.length > 0 && (
          <div className="mt-3 rounded border border-red-500/30 bg-red-500/5 p-2 text-[11px] text-red-800 dark:text-red-300">
            <p className="font-medium">Nothing was imported — fix these rows and re-upload:</p>
            <ul className="mt-1 space-y-0.5">
              {uploadResult.error_rows.map((r, i) => <li key={i}>Row {r.row_number}: {r.error}</li>)}
            </ul>
          </div>
        )}
      </div>

      {!usingPersonal && sections !== null && (
        <div className="card mt-4 !p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1">
              <label className="label" htmlFor="section-picker">{currentLabel ? "Your section" : "Pick your section"}</label>
              {sectionOptions.length === 0 ? (
                <p className="mt-1.5 text-sm text-fg-subtle">No campus timetable has been uploaded yet — or upload your own schedule above.</p>
              ) : (
                <select id="section-picker" className="input mt-1.5" value={pickedKey} onChange={(e) => setPickedKey(e.target.value)}>
                  <option value="">Choose…</option>
                  {sectionOptions.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
                </select>
              )}
            </div>
            {sectionOptions.length > 0 && (
              <button onClick={saveSection} disabled={saving || !pickedKey || pickedKey === `${profile?.school ?? ""} ${profile?.section ?? ""}`} className="btn-primary shrink-0">
                {saving ? "Saving…" : "Save"}
              </button>
            )}
          </div>
          {currentLabel && <p className="mt-2 text-xs text-fg-subtle">Currently showing: {currentLabel}</p>}
        </div>
      )}

      {!usingPersonal && needsSection && sections !== null && sectionOptions.length > 0 && (
        <div className="card mt-4 !p-4 text-sm text-fg-muted">Pick your section above to see your personal schedule.</div>
      )}

      {!usingPersonal && campusEntries !== null && !needsSection && campusEntries.length === 0 && (
        <div className="card mt-8 text-center text-sm text-fg-muted">No classes scheduled yet for your section.</div>
      )}

      {entries.length > 0 && (
        <div className="mt-8 space-y-3">
          {[...byDate.entries()].map(([date, dayEntries]) => (
            <div key={date} className="card !p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">{fmtDate(date)}</p>
              <div className="mt-2 space-y-2">
                {dayEntries
                  .slice()
                  .sort((a, b) => a.start_time.localeCompare(b.start_time))
                  .map((e) => (
                    <div key={e.id} className={`rounded-lg border p-3 ${e.is_cancelled ? "border-red-500/30 bg-red-500/5" : liveNow?.id === e.id ? "border-brand-500/50 bg-brand-500/5" : "border-ink-700 bg-ink-950"}`}>
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
