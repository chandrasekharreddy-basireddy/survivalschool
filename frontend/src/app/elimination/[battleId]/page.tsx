"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError, getAccessToken } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { PageLoader } from "@/components/PageLoader";
import { ExamIntegrityGuard } from "@/components/exams/ExamIntegrityGuard";
import { BattleChat } from "@/components/elimination/BattleChat";

const WS_BASE = process.env.NEXT_PUBLIC_WS_BASE_URL || "ws://localhost:8000";
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

interface Battle {
  id: string; host_id: string; title: string; topic_id: string; status: string; join_code: string;
  current_round_number: number; winner_id: string | null; started_at: string | null; ended_at: string | null;
  scheduled_start_at: string | null; chat_room_id: string | null;
}
interface Participant { user_id: string; full_name: string; public_handle: string | null; status: string; eliminated_at_round: number | null; eliminated_reason: string | null }
interface PersonSearchResult { user_id: string; full_name: string; public_handle: string | null; avatar_url: string | null; relationship: string }
interface RoundOption { id: string; text: string }
interface RoundQuestion { id: string; prompt: string; question_type: string; options: RoundOption[] }
interface CurrentRound { round_number: number; deadline_at: string; question: RoundQuestion; already_answered: boolean; my_is_correct: boolean | null }

type BattleEvent =
  | { event: "battle.started"; battle_id: string }
  | { event: "battle.round_released"; battle_id: string; round_number: number; question: RoundQuestion; deadline_at: string }
  | { event: "battle.answer_result"; battle_id: string; user_id: string; round_number: number; is_correct: boolean }
  | { event: "battle.round_resolved"; battle_id: string; round_number: number; eliminated_user_ids: string[]; survivors_remaining: number }
  | { event: "battle.completed"; battle_id: string; winner_user_id: string | null }
  | { event: "battle.cancelled"; battle_id: string }
  | { event: "battle.participant_eliminated"; battle_id: string; user_id: string; round_number: number; reason: string };

export default function EliminationBattlePage() {
  const params = useParams<{ battleId: string }>();
  const { user, loading } = useAuth();
  const toast = useToast();

  const [battle, setBattle] = useState<Battle | null>(null);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [starting, setStarting] = useState(false);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<PersonSearchResult[]>([]);
  const [inviting, setInviting] = useState<string | null>(null);
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  const [codeCopied, setCodeCopied] = useState(false);

  const [round, setRound] = useState<{ number: number; question: RoundQuestion; deadlineAt: string } | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [myResult, setMyResult] = useState<{ round: number; isCorrect: boolean } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [eliminatedThisRound, setEliminatedThisRound] = useState<string[]>([]);
  const [winnerId, setWinnerId] = useState<string | null | undefined>(undefined);
  const [now, setNow] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const me = participants.find((p) => p.user_id === user?.id);

  const loadState = useCallback(() => {
    apiFetch<Battle>(`/elimination/battles/${params.battleId}`).then(setBattle).catch(() => setBattle(null));
    apiFetch<Participant[]>(`/elimination/battles/${params.battleId}/participants`).then(setParticipants).catch(() => setParticipants([]));
    // REST fallback for the current round — the websocket only ever
    // broadcasts battle.round_released once, at the instant it happens, so
    // this is what actually recovers the question after a refresh or a
    // reconnect that landed after that broadcast already fired.
    apiFetch<CurrentRound | null>(`/elimination/battles/${params.battleId}/round`).then((r) => {
      if (!r) return;
      setRound({ number: r.round_number, question: r.question, deadlineAt: r.deadline_at });
      if (r.already_answered) setMyResult({ round: r.round_number, isCorrect: r.my_is_correct ?? false });
    }).catch(() => {});
  }, [params.battleId]);

  useEffect(() => {
    if (!user) return;
    loadState();
  }, [user, loadState]);

  // Live countdown tick for the current round's deadline.
  useEffect(() => {
    if (!round) return;
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [round]);

  // The QR endpoint requires auth, so a plain <img src> can't carry the
  // token — fetch it manually and hand the browser an object URL instead.
  useEffect(() => {
    if (!battle || battle.status !== "lobby") return;
    const token = getAccessToken();
    if (!token) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    fetch(`${API_BASE}/elimination/battles/${battle.id}/qr`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => {
        if (cancelled || !blob) return;
        objectUrl = URL.createObjectURL(blob);
        setQrUrl(objectUrl);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
    // Re-fetch only when the battle identity/status changes, not on every poll refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [battle?.id, battle?.status]);

  const copyJoinCode = async () => {
    if (!battle) return;
    try {
      await navigator.clipboard.writeText(battle.join_code);
      setCodeCopied(true);
      setTimeout(() => setCodeCopied(false), 1500);
    } catch {
      /* clipboard access denied — the code is still visible to copy by hand */
    }
  };

  useEffect(() => {
    if (!user || !battle) return;
    const token = getAccessToken();
    if (!token) return;
    const ws = new WebSocket(`${WS_BASE}/ws/elimination/${params.battleId}?token=${encodeURIComponent(token)}`);
    wsRef.current = ws;
    ws.onmessage = (msg) => {
      try {
        const evt = JSON.parse(msg.data) as BattleEvent;
        if (evt.event === "battle.started") {
          setBattle((b) => (b ? { ...b, status: "active" } : b));
        } else if (evt.event === "battle.round_released") {
          setRound({ number: evt.round_number, question: evt.question, deadlineAt: evt.deadline_at });
          setSelected([]);
          setMyResult(null);
          setEliminatedThisRound([]);
        } else if (evt.event === "battle.answer_result") {
          if (evt.user_id === user.id) setMyResult({ round: evt.round_number, isCorrect: evt.is_correct });
        } else if (evt.event === "battle.round_resolved") {
          setEliminatedThisRound(evt.eliminated_user_ids);
          loadState();
        } else if (evt.event === "battle.completed") {
          setWinnerId(evt.winner_user_id);
          setBattle((b) => (b ? { ...b, status: "completed" } : b));
          loadState();
        } else if (evt.event === "battle.cancelled") {
          setBattle((b) => (b ? { ...b, status: "cancelled" } : b));
        } else if (evt.event === "battle.participant_eliminated") {
          // Instant, no waiting for the next round_resolved broadcast —
          // an integrity-violation elimination can happen mid-round, not
          // just at round boundaries, so the players list needs to reflect
          // it the moment it happens for everyone watching.
          loadState();
        }
      } catch {
        /* ignore malformed frames */
      }
    };
    return () => ws.close();
    // Reconnect only when the battle identity/status transitions into "active" the first time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, battle?.status === "active", params.battleId]);

  const search = async (q: string) => {
    setSearchQuery(q);
    if (q.trim().length < 2) { setSearchResults([]); return; }
    try {
      const results = await apiFetch<PersonSearchResult[]>(`/follows/search?q=${encodeURIComponent(q.trim())}`);
      setSearchResults(results);
    } catch {
      setSearchResults([]);
    }
  };

  const invite = async (personId: string) => {
    setInviting(personId);
    try {
      await apiFetch(`/elimination/battles/${params.battleId}/invite`, { method: "POST", body: JSON.stringify({ invitee_id: personId }) });
      toast.show("Invitation sent.", "success");
      setSearchResults([]);
      setSearchQuery("");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't send that invitation.", "error");
    } finally {
      setInviting(null);
    }
  };

  const start = async () => {
    setStarting(true);
    try {
      await apiFetch(`/elimination/battles/${params.battleId}/start`, { method: "POST" });
      loadState();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't start the battle.", "error");
    } finally {
      setStarting(false);
    }
  };

  // Zero-tolerance, unlike the contest/AI-Weekly-Exam integrity path (see
  // ExamIntegrityGuard's other usage) which counts violations toward a
  // threshold before auto-submitting — a live head-to-head battle has no
  // "partial credit" fallback the way a written exam does, so a single
  // reported violation eliminates the participant immediately.
  const reportIntegrityEvent = useCallback(
    (eventType: "tab_blur" | "fullscreen_exit" | "copy" | "paste" | "right_click") => {
      apiFetch<{ eliminated: boolean }>(`/elimination/battles/${params.battleId}/integrity-violation`, {
        method: "POST", body: JSON.stringify({ violation_type: eventType }),
      })
        .then((res) => {
          if (res.eliminated) {
            toast.show("You left the exam environment — you've been eliminated.", "error");
            loadState();
          }
        })
        .catch(() => {});
    },
    [params.battleId, toast, loadState],
  );

  // Enter fullscreen the moment the battle goes active, for every
  // still-active participant — a host who was already fullscreen from the
  // lobby doesn't need this, but anyone who joined via a plain link and
  // hasn't triggered a fullscreen gesture yet does.
  useEffect(() => {
    if (battle?.status !== "active" || me?.status !== "active") return;
    if (document.fullscreenElement || !document.documentElement.requestFullscreen) return;
    document.documentElement.requestFullscreen().catch(() => {});
  }, [battle?.status, me?.status]);

  const toggleOption = (optionId: string) => {
    if (!round) return;
    if (round.question.question_type === "multiple") {
      setSelected((prev) => (prev.includes(optionId) ? prev.filter((o) => o !== optionId) : [...prev, optionId]));
    } else {
      setSelected([optionId]);
    }
  };

  const submit = async () => {
    if (!round || selected.length === 0) return;
    setSubmitting(true);
    try {
      const res = await apiFetch<{ is_correct: boolean; eliminated: boolean }>(`/elimination/battles/${params.battleId}/answer`, {
        method: "POST", body: JSON.stringify({ selected_option_ids: selected }),
      });
      setMyResult({ round: round.number, isCorrect: res.is_correct });
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't submit your answer.", "error");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading || !user || !battle) return <div className="mx-auto max-w-2xl px-6 py-16 text-fg-muted"><PageLoader size="md" /></div>;

  const isHost = battle.host_id === user.id;
  const secondsLeft = round && now > 0 ? Math.max(0, Math.ceil((new Date(round.deadlineAt).getTime() - now) / 1000)) : 0;
  const alreadyAnswered = myResult !== null && round !== null && myResult.round === round.number;
  const winner = participants.find((p) => p.user_id === winnerId || p.user_id === battle.winner_id);

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <Link href="/elimination" className="text-sm text-fg-muted hover:text-fg">&larr; All battles</Link>
      <h1 className="mt-2 text-2xl font-bold text-fg">{battle.title}</h1>

      {battle.status === "lobby" && (
        <div className="mt-6 space-y-6">
          {battle.scheduled_start_at && (
            <div className="rounded-lg border border-brand-500/30 bg-brand-500/5 px-4 py-2.5 text-sm text-fg">
              Scheduled to start {new Date(battle.scheduled_start_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
              {" "}— auto-starts once at least one other player has joined.
            </div>
          )}
          <div className="card">
            <h2 className="font-semibold text-fg">Players ({participants.length})</h2>
            <ul className="mt-3 space-y-1.5 text-sm">
              {participants.map((p) => (
                <li key={p.user_id} className="flex items-center justify-between">
                  <span className="text-fg">
                    {p.full_name}
                    {p.public_handle && <span className="text-fg-subtle"> @{p.public_handle}</span>}
                    {p.user_id === battle.host_id ? " (host)" : ""}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <div className="card">
            <h2 className="font-semibold text-fg">Room code</h2>
            <p className="mt-1 text-xs text-fg-subtle">Anyone with this code — or a scan of the QR — can join instantly, no invite or connection required.</p>
            <div className="mt-3 flex items-center gap-4">
              {qrUrl && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={qrUrl} alt="Scan to join this battle" className="h-24 w-24 rounded border border-ink-700 bg-white p-1" />
              )}
              <div>
                <p className="font-mono text-2xl font-bold tracking-widest text-fg">{battle.join_code}</p>
                <button onClick={copyJoinCode} className="btn-secondary !px-3 !py-1 mt-2 text-xs">
                  {codeCopied ? "Copied!" : "Copy code"}
                </button>
              </div>
            </div>
          </div>

          {isHost && (
            <div className="card">
              <h2 className="font-semibold text-fg">Invite friends you follow</h2>
              <p className="mt-1 text-xs text-fg-subtle">Only people you have an accepted connection with show up here — share the room code above for anyone else.</p>
              <input className="input mt-3" placeholder="Search by name or @username…" value={searchQuery} onChange={(e) => search(e.target.value)} />
              {searchResults.length > 0 && (
                <ul className="mt-2 space-y-1.5">
                  {searchResults.map((r) => (
                    <li key={r.user_id} className="flex items-center justify-between rounded-lg border border-ink-700 px-3 py-2 text-sm">
                      <span className="text-fg">
                        {r.full_name}
                        {r.public_handle && <span className="text-fg-subtle"> @{r.public_handle}</span>}
                      </span>
                      <button onClick={() => invite(r.user_id)} disabled={inviting === r.user_id} className="btn-secondary !px-3 !py-1 text-xs">
                        {inviting === r.user_id ? "Inviting…" : "Invite"}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <button onClick={start} disabled={starting || participants.length < 2} className="btn-primary mt-4 w-full">
                {starting ? "Starting…" : "Start battle"}
              </button>
              {participants.length < 2 && <p className="mt-2 text-center text-xs text-fg-subtle">At least one invitee needs to accept before you can start.</p>}
            </div>
          )}
          {!isHost && <p className="text-sm text-fg-subtle">Waiting for the host to start the battle…</p>}

          {battle.chat_room_id && <BattleChat roomId={battle.chat_room_id} />}
        </div>
      )}

      {battle.status === "active" && (
        <ExamIntegrityGuard
          enabled={me?.status === "active"}
          fullscreenRequired={true}
          onIntegrityEvent={reportIntegrityEvent}
        >
        <div className="mt-6 space-y-4">
          {me?.status === "active" && (
            <p className="rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
              This battle is integrity-monitored — leaving fullscreen, switching tabs, or copy/paste eliminates you immediately, no warning.
            </p>
          )}
          {me?.status === "eliminated" ? (
            <div className="card text-center border-red-500/40">
              <p className="text-sm font-medium text-red-700 dark:text-red-400">
                You&apos;ve been eliminated (
                {me.eliminated_reason === "timeout" ? "ran out of time"
                  : me.eliminated_reason === "integrity_violation" ? "left the exam environment"
                  : "wrong answer"}
                ).
              </p>
              <p className="mt-1 text-xs text-fg-subtle">Round {me.eliminated_at_round}. Watching the rest of the battle live below.</p>
            </div>
          ) : null}

          {round ? (
            <div className="card">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-widest text-fg-subtle">Round {round.number}</p>
                <span className={`font-mono text-lg font-bold ${secondsLeft <= 5 ? "text-red-600 dark:text-red-400" : "text-fg"}`}>{secondsLeft}s</span>
              </div>
              <p className="mt-3 font-medium text-fg">{round.question.prompt}</p>
              <div className="mt-4 space-y-2">
                {round.question.options.map((opt) => {
                  const isSelected = selected.includes(opt.id);
                  return (
                    <label key={opt.id} className={`flex cursor-pointer items-center gap-3 rounded-lg border px-4 py-2.5 text-sm transition ${isSelected ? "border-brand-500 bg-brand-500/10 text-brand-700 dark:text-white" : "border-ink-700 text-fg-muted hover:border-ink-600"}`}>
                      <input
                        type={round.question.question_type === "multiple" ? "checkbox" : "radio"}
                        name="battle-option" checked={isSelected}
                        onChange={() => toggleOption(opt.id)}
                        disabled={alreadyAnswered || me?.status === "eliminated" || secondsLeft === 0}
                        className="accent-brand-500"
                      />
                      {opt.text}
                    </label>
                  );
                })}
              </div>
              {alreadyAnswered ? (
                <p className={`mt-4 text-sm font-medium ${myResult?.isCorrect ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}`}>
                  {myResult?.isCorrect ? "Correct — you're through to the next round." : "Wrong — you've been eliminated."}
                </p>
              ) : (
                <button
                  onClick={submit}
                  disabled={submitting || selected.length === 0 || me?.status === "eliminated" || secondsLeft === 0}
                  className="btn-primary mt-4 w-full"
                >
                  {submitting ? "Submitting…" : "Submit answer"}
                </button>
              )}
            </div>
          ) : (
            <div className="card text-center text-sm text-fg-muted">Waiting for the next question…</div>
          )}

          {eliminatedThisRound.length > 0 && (
            <div className="rounded-lg border border-ink-700 px-4 py-2.5 text-xs text-fg-subtle">
              Eliminated this round: {eliminatedThisRound.map((id) => participants.find((p) => p.user_id === id)?.full_name || "a player").join(", ")}
            </div>
          )}

          <div className="card">
            <h2 className="font-semibold text-fg">Players</h2>
            <ul className="mt-3 space-y-1.5 text-sm">
              {participants.map((p) => (
                <li key={p.user_id} className={`flex items-center justify-between ${p.status === "eliminated" ? "opacity-50 line-through" : ""}`}>
                  <span className="text-fg">
                    {p.full_name}
                    {p.public_handle && <span className="text-fg-subtle"> @{p.public_handle}</span>}
                  </span>
                  <span className="text-xs text-fg-subtle">{p.status === "eliminated" ? `out (round ${p.eliminated_at_round})` : p.status}</span>
                </li>
              ))}
            </ul>
          </div>

          {battle.chat_room_id && <BattleChat roomId={battle.chat_room_id} />}
        </div>
        </ExamIntegrityGuard>
      )}

      {battle.status === "completed" && (
        <div className="card mt-6 text-center border-amber-500/40">
          <p className="text-sm uppercase tracking-widest text-fg-subtle">Battle finished</p>
          <p className="mt-2 text-xl font-bold text-fg">
            {winner ? `${winner.full_name} won${winner.user_id === user.id ? " — that's you!" : ""}` : "No winner (everyone was eliminated at once)."}
          </p>
        </div>
      )}

      {battle.status === "cancelled" && (
        <div className="card mt-6 text-center text-sm text-fg-muted">This battle was cancelled — no questions were available for its topic.</div>
      )}
    </div>
  );
}
