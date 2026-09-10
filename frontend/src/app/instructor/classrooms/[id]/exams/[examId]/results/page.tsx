"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { PageLoader } from "@/components/PageLoader";

interface AttemptRow {
  id: string; student_id: string; student_name: string;
  started_at: string; submitted_at: string | null; time_taken_seconds: number | null;
  score_percent: number | null; points_earned: number | null; points_possible: number | null;
  status: string; violation_count: number; warning_count: number;
}

function formatDuration(seconds: number | null) {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

const STATUS_STYLE: Record<string, string> = {
  in_progress: "text-brand-600 dark:text-brand-400 border-brand-500/40",
  submitted: "text-emerald-700 dark:text-emerald-400 border-emerald-500/40",
  terminated: "text-red-600 dark:text-red-400 border-red-500/40",
};

function toCsv(rows: AttemptRow[]): string {
  const header = ["Student", "Status", "Score %", "Points", "Time taken", "Violations", "Warnings"];
  const lines = rows.map((r) => [
    r.student_name, r.status, r.score_percent ?? "", `${r.points_earned ?? ""}/${r.points_possible ?? ""}`,
    formatDuration(r.time_taken_seconds), r.violation_count, r.warning_count,
  ].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(","));
  return [header.join(","), ...lines].join("\n");
}

export default function InstructorExamResultsPage() {
  const { id: classroomId, examId } = useParams<{ id: string; examId: string }>();
  const [rows, setRows] = useState<AttemptRow[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!classroomId || !examId) return;
    apiFetch<AttemptRow[]>(`/classrooms/${classroomId}/exams/${examId}/results`)
      .then(setRows)
      .catch(() => setFailed(true));
  }, [classroomId, examId]);

  const downloadCsv = () => {
    if (!rows) return;
    const blob = new Blob([toCsv(rows)], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "exam-results.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <Link href={`/instructor/classrooms/${classroomId}`} className="text-sm text-brand-600 dark:text-brand-400 hover:underline">&larr; Back to classroom</Link>
      <div className="mt-4 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-fg">Exam results</h1>
        {rows && rows.length > 0 && <button onClick={downloadCsv} className="btn-secondary !px-3 !py-1.5 text-sm">Export CSV</button>}
      </div>

      <div className="mt-6">
        {failed ? (
          <p className="text-sm text-fg-muted">Couldn&apos;t load results.</p>
        ) : rows === null ? (
          <PageLoader size="sm" />
        ) : rows.length === 0 ? (
          <div className="rounded-lg border border-dashed border-ink-700 p-12 text-center text-sm text-fg-subtle">
            No attempts yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ink-700 text-left text-xs uppercase text-fg-subtle">
                  <th className="pb-2 pr-4">Student</th>
                  <th className="pb-2 pr-4">Status</th>
                  <th className="pb-2 pr-4">Score</th>
                  <th className="pb-2 pr-4">Points</th>
                  <th className="pb-2 pr-4">Time</th>
                  <th className="pb-2">Flags</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-ink-800">
                    <td className="py-2.5 pr-4 text-fg">{r.student_name}</td>
                    <td className="py-2.5 pr-4">
                      <span className={`rounded-full border px-2 py-0.5 text-xs ${STATUS_STYLE[r.status] || ""}`}>{r.status.replace("_", " ")}</span>
                    </td>
                    <td className="py-2.5 pr-4 font-medium text-fg">{r.score_percent != null ? `${r.score_percent}%` : "—"}</td>
                    <td className="py-2.5 pr-4 text-fg-muted">{r.points_earned ?? "—"}/{r.points_possible ?? "—"}</td>
                    <td className="py-2.5 pr-4 text-fg-subtle">{formatDuration(r.time_taken_seconds)}</td>
                    <td className="py-2.5 text-fg-subtle">
                      {r.violation_count > 0 ? `${r.violation_count} violation${r.violation_count !== 1 ? "s" : ""}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
