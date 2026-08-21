"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatRelative } from "@/lib/format";

interface Battle {
  id: string; host_id: string; title: string; topic_id: string; status: string;
  current_round_number: number; winner_id: string | null; started_at: string | null; ended_at: string | null;
  scheduled_start_at: string | null;
}
interface Invitation {
  id: string; battle_id: string; battle_title: string; inviter_id: string; inviter_name: string; inviter_handle: string | null;
  invitee_id: string; status: string; created_at: string;
}

const STATUS_LABEL: Record<string, string> = { lobby: "Waiting to start", active: "In progress", completed: "Finished", cancelled: "Cancelled" };

export default function EliminationPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const toast = useToast();

  const [battles, setBattles] = useState<Battle[] | null>(null);
  const [invitations, setInvitations] = useState<Invitation[] | null>(null);
  const [subjectName, setSubjectName] = useState("");
  const [topicName, setTopicName] = useState("");
  const [title, setTitle] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [creating, setCreating] = useState(false);
  const [joinCode, setJoinCode] = useState("");

  const refresh = () => {
    apiFetch<Battle[]>("/elimination/battles/me").then(setBattles).catch(() => setBattles([]));
    apiFetch<Invitation[]>("/elimination/invitations/incoming").then(setInvitations).catch(() => setInvitations([]));
  };

  useEffect(() => {
    if (!user) return;
    refresh();
  }, [user]);

  const createBattle = async () => {
    if (!title.trim() || !subjectName.trim() || !topicName.trim()) return;
    setCreating(true);
    try {
      const battle = await apiFetch<Battle>("/elimination/battles", {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(), subject_name: subjectName.trim(), topic_name: topicName.trim(),
          scheduled_start_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
        }),
      });
      router.push(`/elimination/${battle.id}`);
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't create the battle.", "error");
    } finally {
      setCreating(false);
    }
  };

  const respond = async (invitationId: string, accept: boolean) => {
    try {
      const inv = await apiFetch<Invitation>(`/elimination/invitations/${invitationId}/${accept ? "accept" : "decline"}`, { method: "POST" });
      refresh();
      if (accept) router.push(`/elimination/${inv.battle_id}`);
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't respond to that invitation.", "error");
    }
  };

  if (loading) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to host or join an elimination battle.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Elimination battles</h1>
      <p className="mt-1 text-sm text-fg-muted">
        Invite friends by name, one question at a time with a strict 15-second deadline. Miss it or answer wrong and
        you&apos;re out — last one standing wins.
      </p>

      <div className="card mt-6 !p-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <p className="shrink-0 text-sm font-medium text-fg">Have a room code?</p>
        <div className="flex flex-1 gap-2">
          <input
            className="input flex-1 font-mono uppercase tracking-widest"
            placeholder="ABC123"
            maxLength={8}
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
            onKeyDown={(e) => { if (e.key === "Enter" && joinCode.trim()) router.push(`/elimination/join/${joinCode.trim()}`); }}
          />
          <button
            onClick={() => router.push(`/elimination/join/${joinCode.trim()}`)}
            disabled={!joinCode.trim()}
            className="btn-secondary shrink-0"
          >
            Join
          </button>
        </div>
      </div>

      <div className="card mt-4">
        <h2 className="font-semibold text-fg">Start a new battle</h2>
        <p className="mt-1 text-xs text-fg-subtle">Type any subject and topic — AI generates the question pool for you.</p>
        <input className="input mt-3" placeholder="Battle title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <input className="input" placeholder="Subject (e.g. Computer Science)" value={subjectName} onChange={(e) => setSubjectName(e.target.value)} />
          <input className="input" placeholder="Topic (e.g. Graph Algorithms)" value={topicName} onChange={(e) => setTopicName(e.target.value)} />
        </div>
        <div className="mt-3">
          <label className="label" htmlFor="scheduled_at">Schedule start (optional)</label>
          <input
            id="scheduled_at" type="datetime-local" className="input mt-1.5"
            value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)}
          />
          <p className="mt-1 text-xs text-fg-subtle">
            {scheduledAt ? "The battle auto-starts at this time once at least one other player has joined." : "Leave blank to start it yourself whenever you're ready."}
          </p>
        </div>
        <button onClick={createBattle} disabled={creating || !title.trim() || !subjectName.trim() || !topicName.trim()} className="btn-primary mt-3">
          {creating ? "Creating…" : "Create battle"}
        </button>
      </div>

      {invitations !== null && invitations.length > 0 && (
        <div className="mt-8">
          <h2 className="font-semibold text-fg">Invitations</h2>
          <div className="mt-3 space-y-2">
            {invitations.map((inv) => (
              <div key={inv.id} className="card !p-4 flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="truncate font-medium text-fg">{inv.battle_title}</p>
                  <p className="text-xs text-fg-subtle">
                    from {inv.inviter_name}{inv.inviter_handle ? ` (@${inv.inviter_handle})` : ""} · {formatRelative(inv.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <button onClick={() => respond(inv.id, true)} className="btn-primary !px-3 !py-1.5 text-sm">Accept</button>
                  <button onClick={() => respond(inv.id, false)} className="btn-secondary !px-3 !py-1.5 text-sm">Decline</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-8">
        <h2 className="font-semibold text-fg">Your battles</h2>
        {battles === null && <p className="mt-2 text-sm text-fg-subtle">Loading…</p>}
        {battles !== null && battles.length === 0 && <p className="mt-2 text-sm text-fg-subtle">No battles yet — create one above.</p>}
        <div className="mt-3 space-y-2">
          {battles?.map((b) => (
            <Link key={b.id} href={`/elimination/${b.id}`} className="card !p-4 flex items-center justify-between gap-4 transition hover:border-brand-500/50">
              <div className="min-w-0">
                <p className="truncate font-medium text-fg">{b.title}</p>
                <p className="text-xs text-fg-subtle">{b.host_id === user.id ? "Hosted by you" : "Joined"}{b.status === "active" ? ` · round ${b.current_round_number}` : ""}</p>
              </div>
              <span className="shrink-0 rounded-full border border-ink-700 px-2.5 py-1 text-xs font-medium text-fg-muted">{STATUS_LABEL[b.status] || b.status}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
