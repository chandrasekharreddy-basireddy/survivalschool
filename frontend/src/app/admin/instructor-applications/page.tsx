"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { PageLoader } from "@/components/PageLoader";

interface InstructorApplicationOut {
  id: string;
  user_id: string;
  applicant_email: string;
  applicant_name: string;
  institution: string | null;
  reason: string;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  reviewed_at: string | null;
  review_note: string | null;
}

type StatusFilter = "pending" | "approved" | "rejected" | "all";

const TABS: { key: StatusFilter; label: string }[] = [
  { key: "pending", label: "Pending" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
  { key: "all", label: "All" },
];

export default function InstructorApplicationsPage() {
  const { user, loading } = useAuth();
  const toast = useToast();
  const [filter, setFilter] = useState<StatusFilter>("pending");
  const [applications, setApplications] = useState<InstructorApplicationOut[] | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = (status: StatusFilter) => {
    setApplications(null);
    apiFetch<InstructorApplicationOut[]>(`/admin/instructor-applications?status=${status}`)
      .then(setApplications)
      .catch(() => setApplications([]));
  };

  useEffect(() => {
    if (user) load(filter);
  }, [user, filter]);

  const review = async (application: InstructorApplicationOut, action: "approve" | "reject") => {
    setBusyId(application.id);
    try {
      await apiFetch(`/admin/instructor-applications/${application.id}/${action}`, {
        method: "POST",
        body: JSON.stringify({ note: notes[application.id]?.trim() || null }),
      });
      toast.show(
        action === "approve"
          ? `${application.applicant_name} is now an instructor.`
          : `${application.applicant_name}'s application was rejected.`,
        "success"
      );
      setApplications((prev) => (prev ? prev.filter((a) => a.id !== application.id) : prev));
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't update this application.", "error");
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <div className="mx-auto max-w-4xl px-6 py-16 text-fg-muted"><PageLoader size="md" /></div>;
  if (!user || !user.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r))) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">This area is for admins.</p>
        <Link href="/dashboard" className="btn-secondary mt-6 inline-flex">Back to dashboard</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-fg">Instructor applications</h1>
        <Link href="/admin" className="text-sm text-brand-600 dark:text-brand-400 hover:underline">Admin console &rarr;</Link>
      </div>
      <p className="mt-1 text-sm text-fg-muted">
        Approving grants the INSTRUCTOR role through the same audited path as manual role assignment.
      </p>

      <div className="mt-6 flex gap-1 border-b border-ink-800">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setFilter(t.key)}
            className={`rounded-t-lg px-3 py-2 text-sm font-medium transition-colors ${
              filter === t.key ? "border-b-2 border-brand-600 text-fg dark:border-brand-400" : "text-fg-muted hover:text-fg"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-6 space-y-4">
        {applications === null && <p className="text-sm text-fg-subtle"><PageLoader size="sm" /></p>}
        {applications !== null && applications.length === 0 && (
          <p className="text-sm text-fg-subtle">No {filter === "all" ? "" : filter} applications.</p>
        )}
        {applications?.map((a) => (
          <div key={a.id} className="card">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="font-semibold text-fg">{a.applicant_name}</p>
                <p className="text-sm text-fg-muted">{a.applicant_email}</p>
                {a.institution && <p className="text-sm text-fg-subtle">{a.institution}</p>}
              </div>
              <div className="text-right text-xs text-fg-subtle">
                <p>Applied {new Date(a.created_at).toLocaleDateString()}</p>
                <span
                  className={`mt-1 inline-block rounded px-1.5 py-0.5 text-[11px] font-medium ${
                    a.status === "approved"
                      ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                      : a.status === "rejected"
                        ? "bg-red-500/10 text-red-700 dark:text-red-400"
                        : "bg-ink-800 text-fg-muted"
                  }`}
                >
                  {a.status}
                </span>
              </div>
            </div>
            <p className="mt-3 whitespace-pre-wrap text-sm text-fg">{a.reason}</p>
            {a.review_note && (
              <p className="mt-2 text-xs text-fg-subtle">Review note: {a.review_note}</p>
            )}
            {a.status === "pending" && (
              <div className="mt-4 space-y-2">
                <input
                  className="input"
                  placeholder="Optional note for this decision"
                  value={notes[a.id] ?? ""}
                  onChange={(e) => setNotes((prev) => ({ ...prev, [a.id]: e.target.value }))}
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => review(a, "approve")}
                    disabled={busyId === a.id}
                    className="btn-primary !py-1.5 text-sm"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => review(a, "reject")}
                    disabled={busyId === a.id}
                    className="btn-secondary !py-1.5 text-sm"
                  >
                    Reject
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
