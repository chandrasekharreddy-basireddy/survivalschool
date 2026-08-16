"use client";

import { useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { RoleGate } from "@/components/RoleGate";

interface Course { id: string; title: string; is_published: boolean }
interface Schedule { id: string; day_of_week: number; time_slot: string; duration_minutes: number; question_count: number; auto_certificate_top_n: number; course_id: string; difficulty: string; is_active: boolean; title_prefix: string; last_occurrence_key: string | null }

const dayNames = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export default function ExamSchedulerPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [courseId, setCourseId] = useState("");
  const [dayOfWeek, setDayOfWeek] = useState(5);
  const [timeSlot, setTimeSlot] = useState("10:00");
  const [duration, setDuration] = useState(60);
  const [questionCount, setQuestionCount] = useState(10);
  const [topN, setTopN] = useState(3);
  const [difficulty, setDifficulty] = useState("mixed");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [courseRows, scheduleRows] = await Promise.all([
        apiFetch<Course[]>("/courses?published_only=false"),
        apiFetch<Schedule[]>("/exams/schedules"),
      ]);
      setCourses(courseRows);
      setSchedules(scheduleRows);
      setCourseId((current) => current || courseRows[0]?.id || "");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to load scheduler data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!courseId) return;
    setSaving(true);
    setError(null);
    try {
      await apiFetch<Schedule>("/exams/schedules", {
        method: "POST",
        body: JSON.stringify({ day_of_week: dayOfWeek, time_slot: timeSlot, duration_minutes: duration, question_count: questionCount, auto_certificate_top_n: topN, course_id: courseId, difficulty, title_prefix: "Weekend AI Exam", is_active: true }),
      });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to create schedule.");
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (schedule: Schedule) => {
    try {
      await apiFetch<Schedule>(`/exams/schedules/${schedule.id}`, {
        method: "PATCH",
        body: JSON.stringify({ day_of_week: schedule.day_of_week, time_slot: schedule.time_slot, duration_minutes: schedule.duration_minutes, question_count: schedule.question_count, auto_certificate_top_n: schedule.auto_certificate_top_n, course_id: schedule.course_id, difficulty: schedule.difficulty, title_prefix: schedule.title_prefix, is_active: !schedule.is_active }),
      });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to update schedule.");
    }
  };

  return (
    <RoleGate roles={["ADMIN", "SUPER_ADMIN"]}>
      <div className="page-frame">
        <header className="page-header">
          <p className="mb-2 text-[0.68rem] font-extrabold uppercase tracking-[0.18em] text-brand-400">EXAM CONTROL</p>
          <h1>Weekend AI exam scheduler</h1>
          <p className="mt-2 max-w-2xl text-sm text-fg-muted">Configure Saturday and Sunday IST exam slots. The worker creates each occurrence idempotently and finalizes expired attempts server-side.</p>
        </header>

        {error && <p role="alert" className="mb-4 border-l-2 border-red-400 bg-red-400/10 px-3 py-2 text-sm text-red-300">{error}</p>}

        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_1.35fr]">
          <section className="section-card">
            <h2>Create a schedule</h2>
            <div className="mt-4 grid gap-4">
              <div><label className="label" htmlFor="course">Course</label><select id="course" className="input" value={courseId} onChange={(e) => setCourseId(e.target.value)}><option value="">Choose a course</option>{courses.map((c) => <option key={c.id} value={c.id}>{c.title}{c.is_published ? "" : " (draft)"}</option>)}</select></div>
              <div className="grid gap-4 sm:grid-cols-2"><div><label className="label" htmlFor="day">Day</label><select id="day" className="input" value={dayOfWeek} onChange={(e) => setDayOfWeek(Number(e.target.value))}><option value={5}>Saturday</option><option value={6}>Sunday</option></select></div><div><label className="label" htmlFor="time">IST start</label><input id="time" type="time" className="input" value={timeSlot} onChange={(e) => setTimeSlot(e.target.value)} /></div></div>
              <div className="grid gap-4 sm:grid-cols-3"><div><label className="label" htmlFor="duration">Minutes</label><input id="duration" type="number" min={15} max={240} className="input" value={duration} onChange={(e) => setDuration(Number(e.target.value))} /></div><div><label className="label" htmlFor="count">Questions</label><input id="count" type="number" min={1} max={50} className="input" value={questionCount} onChange={(e) => setQuestionCount(Number(e.target.value))} /></div><div><label className="label" htmlFor="topn">Top certificates</label><input id="topn" type="number" min={0} max={10} className="input" value={topN} onChange={(e) => setTopN(Number(e.target.value))} /></div></div>
              <div><label className="label" htmlFor="difficulty">Difficulty</label><select id="difficulty" className="input" value={difficulty} onChange={(e) => setDifficulty(e.target.value)}><option value="mixed">Mixed</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></div>
              <button className="btn-primary w-full" disabled={saving || loading || !courseId} onClick={create}>{saving ? "Saving…" : "Add schedule"}</button>
            </div>
          </section>

          <section className="section-card">
            <div className="flex items-center justify-between gap-3"><div><h2>Active schedules</h2><p className="mt-1 text-sm text-fg-subtle">Saturday and Sunday slots are interpreted in Asia/Kolkata.</p></div><span className="game-badge">{schedules.length} configured</span></div>
            <div className="mt-4 overflow-x-auto"><table><thead><tr><th>Day</th><th>Time</th><th>Course</th><th>Duration</th><th>Status</th></tr></thead><tbody>{schedules.map((schedule) => { const course = courses.find((c) => c.id === schedule.course_id); return <tr key={schedule.id}><td>{dayNames[schedule.day_of_week]}</td><td className="font-mono">{schedule.time_slot}</td><td>{course?.title ?? schedule.course_id}</td><td>{schedule.duration_minutes} min</td><td><button onClick={() => toggle(schedule)} className="text-sm font-bold text-brand-300 hover:underline">{schedule.is_active ? "Active" : "Paused"}</button></td></tr>; })}</tbody></table></div>
          </section>
        </div>
      </div>
    </RoleGate>
  );
}
