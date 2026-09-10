"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";
import { PageLoader } from "@/components/PageLoader";

interface Classroom {
  id: string;
  name: string;
  description: string;
  section: string;
  join_code: string;
  lecturer_name: string;
  member_count: number;
  exam_count: number;
  is_active: boolean;
  created_at: string;
}

export default function ClassroomsPage() {
  const { user, loading } = useAuth();
  const [classrooms, setClassrooms] = useState<Classroom[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [joinCode, setJoinCode] = useState("");
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState("");
  const [joinSuccess, setJoinSuccess] = useState("");

  const loadClassrooms = () => {
    setFailed(false);
    apiFetch<Classroom[]>("/classrooms/enrolled")
      .then(setClassrooms)
      .catch(() => setFailed(true));
  };

  useEffect(() => {
    if (user) loadClassrooms();
  }, [user]);

  const handleJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!joinCode.trim()) return;
    setJoining(true);
    setJoinError("");
    setJoinSuccess("");
    try {
      const c = await apiFetch<Classroom>("/classrooms/join", {
        method: "POST",
        body: JSON.stringify({ join_code: joinCode.trim().toUpperCase() }),
      });
      setJoinSuccess(`Joined "${c.name}" successfully!`);
      setJoinCode("");
      loadClassrooms();
    } catch (err: any) {
      setJoinError(err?.message || "Failed to join classroom.");
    } finally {
      setJoining(false);
    }
  };

  if (loading) return <div className="mx-auto max-w-6xl px-6 py-16"><PageLoader size="md" /></div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to view your classrooms.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-fg">My Classrooms</h1>
          <p className="mt-1 text-sm text-fg-muted">Join a classroom with a code from your instructor, or browse your enrolled classes.</p>
        </div>
      </div>

      <form onSubmit={handleJoin} className="mt-6 flex gap-3">
        <input
          type="text"
          value={joinCode}
          onChange={e => setJoinCode(e.target.value.toUpperCase())}
          placeholder="Enter join code"
          maxLength={8}
          className="w-40 rounded-lg border border-ink-700 bg-ink-900 px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:border-brand-500 focus:outline-none"
        />
        <button type="submit" disabled={joining || !joinCode.trim()} className="btn-primary !px-5 disabled:opacity-50">
          {joining ? "Joining..." : "Join"}
        </button>
      </form>
      {joinError && <p className="mt-2 text-sm text-red-400">{joinError}</p>}
      {joinSuccess && <p className="mt-2 text-sm text-emerald-400">{joinSuccess}</p>}

      <div className="mt-8">
        {failed ? (
          <div className="card !p-4 flex items-center justify-between gap-3">
            <p className="text-sm text-fg-muted">Couldn&apos;t load classrooms.</p>
            <button type="button" onClick={loadClassrooms} className="btn-secondary shrink-0">Retry</button>
          </div>
        ) : classrooms === null ? (
          <PageLoader size="sm" />
        ) : classrooms.length === 0 ? (
          <div className="rounded-lg border border-dashed border-ink-700 p-12 text-center text-sm text-fg-subtle">
            You haven&apos;t joined any classrooms yet. Ask your instructor for a join code.
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {classrooms.map(c => (
              <Link key={c.id} href={`/classrooms/${c.id}`} className="card transition hover:border-brand-500/50">
                <h3 className="font-semibold text-fg">{c.name}</h3>
                {c.section && <p className="mt-0.5 text-xs text-fg-subtle">Section: {c.section}</p>}
                <p className="mt-2 text-sm text-fg-muted line-clamp-2">{c.description || "No description"}</p>
                <div className="mt-4 flex items-center gap-4 text-xs text-fg-subtle">
                  <span>By {c.lecturer_name}</span>
                  <span>{c.member_count} student{c.member_count !== 1 ? "s" : ""}</span>
                  <span>{c.exam_count} exam{c.exam_count !== 1 ? "s" : ""}</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
