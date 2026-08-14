"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

interface Course { id: string; title: string }
interface RosterRow { student_id: string; student_name: string; status: string; method: string }
interface TimetableEntry {
  id: string;
  course_id: string;
  course_title: string;
  term: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  room: string;
  session_type: string;
}

export default function InstructorTimetablePage() {
  const { user, loading } = useAuth();
  const toast = useToast();
  const [courses, setCourses] = useState<Course[]>([]);
  const [entries, setEntries] = useState<TimetableEntry[]>([]);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    course_id: "", term: "2026-Fall", term_start_date: "", term_end_date: "",
    day_of_week: 0, start_time: "09:00", end_time: "10:00", room: "", session_type: "lecture",
  });

  const load = async () => {
    if (!user) return;
    // published_only=false, scoped server-side to "my own courses" for a
    // non-admin instructor — see courses.py's list_courses — so this single
    // call already returns every course (draft or published) this instructor
    // can schedule a class for.
    const mine = await apiFetch<Course[]>("/courses?published_only=false").catch(() => []);
    setCourses(mine);
    if (mine.length > 0 && !form.course_id) setForm((f) => ({ ...f, course_id: mine[0].id }));

    const list = await apiFetch<TimetableEntry[]>("/timetable/me").catch(() => []);
    setEntries(list);
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const submit = async () => {
    setSaving(true);
    try {
      await apiFetch("/timetable", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          start_time: `${form.start_time}:00`,
          end_time: `${form.end_time}:00`,
        }),
      });
      toast.show("Timetable entry created.", "success");
      await load();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't create entry.", "error");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await apiFetch(`/timetable/${id}`, { method: "DELETE" });
      setEntries((prev) => prev.filter((e) => e.id !== id));
      toast.show("Entry removed.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't remove entry.", "error");
    }
  };

  const [attendance, setAttendance] = useState<Record<string, { sessionId: string; code: string; codeExpiresAt: string }>>({});
  const [roster, setRoster] = useState<Record<string, RosterRow[]>>({});
  const [marking, setMarking] = useState<string | null>(null);

  const openAttendance = async (entryId: string) => {
    try {
      const session = await apiFetch<{ id: string; check_in_code: string; code_expires_at: string }>(
        "/attendance/sessions/open", { method: "POST", body: JSON.stringify({ timetable_entry_id: entryId }) }
      );
      setAttendance((prev) => ({ ...prev, [entryId]: { sessionId: session.id, code: session.check_in_code, codeExpiresAt: session.code_expires_at } }));
      const roll = await apiFetch<RosterRow[]>(`/attendance/sessions/${session.id}`);
      setRoster((prev) => ({ ...prev, [entryId]: roll }));
      toast.show("Attendance opened — share the code with the class.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't open attendance (only works on the class's scheduled day).", "error");
    }
  };

  const refreshRoster = async (entryId: string) => {
    const session = attendance[entryId];
    if (!session) return;
    const roll = await apiFetch<RosterRow[]>(`/attendance/sessions/${session.sessionId}`).catch(() => []);
    setRoster((prev) => ({ ...prev, [entryId]: roll }));
  };

  const markStatus = async (entryId: string, studentId: string, status: string) => {
    const session = attendance[entryId];
    if (!session) return;
    setMarking(studentId);
    try {
      await apiFetch(`/attendance/sessions/${session.sessionId}/mark`, {
        method: "POST", body: JSON.stringify({ student_id: studentId, status }),
      });
      await refreshRoster(entryId);
      toast.show("Attendance updated.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't update attendance.", "error");
    } finally {
      setMarking(null);
    }
  };

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState({ term: "", day_of_week: 0, start_time: "09:00", end_time: "10:00", room: "" });
  const [savingEdit, setSavingEdit] = useState(false);

  const startEdit = (e: TimetableEntry) => {
    setEditingId(e.id);
    setEditDraft({ term: e.term, day_of_week: e.day_of_week, start_time: e.start_time.slice(0, 5), end_time: e.end_time.slice(0, 5), room: e.room || "" });
  };

  const saveEdit = async (entryId: string) => {
    setSavingEdit(true);
    try {
      const updated = await apiFetch<TimetableEntry>(`/timetable/${entryId}`, {
        method: "PATCH",
        body: JSON.stringify({
          term: editDraft.term, day_of_week: editDraft.day_of_week,
          start_time: `${editDraft.start_time}:00`, end_time: `${editDraft.end_time}:00`, room: editDraft.room,
        }),
      });
      setEntries((prev) => prev.map((e) => (e.id === entryId ? updated : e)));
      setEditingId(null);
      toast.show("Timetable entry updated.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't update that entry — check for a scheduling conflict.", "error");
    } finally {
      setSavingEdit(false);
    }
  };

  if (loading) return <div className="mx-auto max-w-4xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user || !user.roles.some((r) => ["INSTRUCTOR", "ADMIN", "SUPER_ADMIN"].includes(r))) {
    return <div className="mx-auto max-w-md px-6 py-24 text-center text-fg-muted">Instructor access required.</div>;
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Manage timetable</h1>
      <p className="mt-1 text-sm text-fg-muted">
        Overlapping slots for the same instructor or the same room are rejected automatically — the server checks this on every save.
      </p>

      <div className="card mt-6 space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label">Course</label>
            <select className="input" value={form.course_id} onChange={(e) => setForm({ ...form, course_id: e.target.value })}>
              {courses.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Term</label>
            <input className="input" value={form.term} onChange={(e) => setForm({ ...form, term: e.target.value })} placeholder="2026-Fall" />
          </div>
          <div>
            <label className="label">Term start date</label>
            <input type="date" className="input" value={form.term_start_date} onChange={(e) => setForm({ ...form, term_start_date: e.target.value })} />
          </div>
          <div>
            <label className="label">Term end date</label>
            <input type="date" className="input" value={form.term_end_date} onChange={(e) => setForm({ ...form, term_end_date: e.target.value })} />
          </div>
          <div>
            <label className="label">Day of week</label>
            <select className="input" value={form.day_of_week} onChange={(e) => setForm({ ...form, day_of_week: Number(e.target.value) })}>
              {DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Session type</label>
            <select className="input" value={form.session_type} onChange={(e) => setForm({ ...form, session_type: e.target.value })}>
              <option value="lecture">Lecture</option>
              <option value="lab">Lab</option>
              <option value="seminar">Seminar</option>
              <option value="exam">Exam</option>
            </select>
          </div>
          <div>
            <label className="label">Start time</label>
            <input type="time" className="input" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} />
          </div>
          <div>
            <label className="label">End time</label>
            <input type="time" className="input" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} />
          </div>
          <div className="sm:col-span-2">
            <label className="label">Room</label>
            <input className="input" value={form.room} onChange={(e) => setForm({ ...form, room: e.target.value })} placeholder="Room 204" />
          </div>
        </div>
        <button
          onClick={submit}
          disabled={saving || !form.course_id || !form.term_start_date || !form.term_end_date}
          className="btn-primary"
        >
          {saving ? "Saving…" : "Add timetable entry"}
        </button>
      </div>

      <h2 className="mt-8 font-semibold text-fg">Your scheduled classes</h2>
      <div className="mt-3 space-y-2">
        {entries.length === 0 && <p className="text-sm text-fg-subtle">No entries yet.</p>}
        {entries.map((e) => (
          <div key={e.id} className="card !p-4">
            {editingId === e.id ? (
              <div className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="label">Term</label>
                    <input className="input !py-1.5 text-sm" value={editDraft.term} onChange={(ev) => setEditDraft({ ...editDraft, term: ev.target.value })} />
                  </div>
                  <div>
                    <label className="label">Day</label>
                    <select className="input !py-1.5 text-sm" value={editDraft.day_of_week} onChange={(ev) => setEditDraft({ ...editDraft, day_of_week: Number(ev.target.value) })}>
                      {DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="label">Start</label>
                    <input type="time" className="input !py-1.5 text-sm" value={editDraft.start_time} onChange={(ev) => setEditDraft({ ...editDraft, start_time: ev.target.value })} />
                  </div>
                  <div>
                    <label className="label">End</label>
                    <input type="time" className="input !py-1.5 text-sm" value={editDraft.end_time} onChange={(ev) => setEditDraft({ ...editDraft, end_time: ev.target.value })} />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="label">Room</label>
                    <input className="input !py-1.5 text-sm" value={editDraft.room} onChange={(ev) => setEditDraft({ ...editDraft, room: ev.target.value })} />
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => saveEdit(e.id)} disabled={savingEdit} className="btn-primary !px-3 !py-1.5 text-xs">
                    {savingEdit ? "Saving…" : "Save changes"}
                  </button>
                  <button onClick={() => setEditingId(null)} className="btn-secondary !px-3 !py-1.5 text-xs">Cancel</button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-fg">{e.course_title}</p>
                  <p className="text-xs text-fg-subtle">
                    {DAYS[e.day_of_week]} · {e.start_time.slice(0, 5)}–{e.end_time.slice(0, 5)} · {e.room || "TBD"} · {e.term}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => openAttendance(e.id)} className="btn-secondary !px-3 !py-1.5 text-xs">
                    {attendance[e.id] ? "Reopen attendance" : "Open attendance"}
                  </button>
                  <button onClick={() => startEdit(e)} className="btn-secondary !px-3 !py-1.5 text-xs">Edit</button>
                  <button onClick={() => remove(e.id)} className="btn-secondary !px-3 !py-1.5 text-xs">Remove</button>
                </div>
              </div>
            )}
            {attendance[e.id] && (
              <div className="mt-3 rounded-lg border border-brand-500/40 bg-brand-500/5 p-3">
                <p className="text-xs text-fg-subtle">Check-in code (valid 15 minutes) — share it aloud or on screen:</p>
                <p className="mt-1 font-mono text-2xl font-bold tracking-widest text-brand-400">{attendance[e.id].code}</p>
                <div className="mt-2 flex items-center justify-between">
                  <p className="text-xs text-fg-subtle">{(roster[e.id] || []).length} checked in</p>
                  <button onClick={() => refreshRoster(e.id)} className="text-xs text-brand-400 hover:underline">Refresh roster</button>
                </div>
                {(roster[e.id] || []).length > 0 && (
                  <ul className="mt-2 space-y-1.5">
                    {(roster[e.id] || []).map((r) => (
                      <li key={r.student_id} className="flex items-center justify-between text-xs text-fg-muted">
                        <span>{r.student_name}</span>
                        <select
                          className="rounded border border-ink-700 bg-ink-950 px-1.5 py-0.5 text-xs capitalize text-fg-muted"
                          value={r.status}
                          disabled={marking === r.student_id}
                          onChange={(ev) => markStatus(e.id, r.student_id, ev.target.value)}
                        >
                          <option value="present">Present</option>
                          <option value="absent">Absent</option>
                          <option value="excused">Excused</option>
                        </select>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="mt-2 text-[11px] text-fg-subtle">
                  Only students who&apos;ve checked in appear here — override their status if needed.
                </p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
