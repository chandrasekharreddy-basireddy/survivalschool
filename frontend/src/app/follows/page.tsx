"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { formatRelative } from "@/lib/format";
import { initials } from "@/lib/avatar";
import { PageLoader } from "@/components/PageLoader";

interface FollowRequestOut {
  id: string; requester_id: string; requester_name: string; requester_handle: string | null;
  target_id: string; target_name: string; target_handle: string | null;
  status: string; created_at: string; responded_at: string | null;
}
interface ConnectionOut { user_id: string; full_name: string; public_handle: string | null; avatar_url: string | null; connected_since: string }
interface PersonResult { user_id: string; full_name: string; public_handle: string | null; avatar_url: string | null; relationship: string }

type Tab = "connections" | "requests" | "find";

function Avatar({ name, url }: { name: string; url: string | null }) {
  // eslint-disable-next-line @next/next/no-img-element -- user-uploaded avatar from arbitrary storage URL, not a static/known-dimension asset next/image needs
  if (url) return <img src={url} alt="" className="h-10 w-10 shrink-0 rounded-full object-cover" />;
  return (
    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ink-800 text-sm font-semibold text-fg-muted">
      {initials(name)}
    </span>
  );
}

export default function FollowsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("connections");
  const [connections, setConnections] = useState<ConnectionOut[] | null>(null);
  const [incoming, setIncoming] = useState<FollowRequestOut[] | null>(null);
  const [outgoing, setOutgoing] = useState<FollowRequestOut[] | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PersonResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const loadConnections = () => apiFetch<ConnectionOut[]>("/follows/connections").then(setConnections).catch(() => setConnections([]));
  const loadIncoming = () => apiFetch<FollowRequestOut[]>("/follows/requests/incoming").then(setIncoming).catch(() => setIncoming([]));
  const loadOutgoing = () => apiFetch<FollowRequestOut[]>("/follows/requests/outgoing").then(setOutgoing).catch(() => setOutgoing([]));

  useEffect(() => {
    if (!user) return;
    loadConnections();
    loadIncoming();
    loadOutgoing();
  }, [user]);

  const search = async () => {
    if (query.trim().length < 2) {
      toast.show("Type at least 2 characters.", "error");
      return;
    }
    setSearching(true);
    try {
      const r = await apiFetch<PersonResult[]>(`/follows/search?q=${encodeURIComponent(query.trim())}`);
      setResults(r);
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Search failed.", "error");
    } finally {
      setSearching(false);
    }
  };

  const sendRequest = async (targetId: string) => {
    setBusyId(targetId);
    try {
      await apiFetch("/follows/requests", { method: "POST", body: JSON.stringify({ target_id: targetId }) });
      toast.show("Follow request sent.", "success");
      setResults((prev) => prev && prev.map((p) => (p.user_id === targetId ? { ...p, relationship: "pending_outgoing" } : p)));
      loadOutgoing();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't send request.", "error");
    } finally {
      setBusyId(null);
    }
  };

  const respond = async (requestId: string, action: "accept" | "decline") => {
    setBusyId(requestId);
    try {
      await apiFetch(`/follows/requests/${requestId}/${action}`, { method: "POST" });
      toast.show(action === "accept" ? "Connected — you can now message each other." : "Request declined.", "success");
      loadIncoming();
      loadConnections();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't update this request.", "error");
    } finally {
      setBusyId(null);
    }
  };

  const cancelRequest = async (requestId: string) => {
    setBusyId(requestId);
    try {
      await apiFetch(`/follows/requests/${requestId}`, { method: "DELETE" });
      toast.show("Request cancelled.", "success");
      loadOutgoing();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't cancel.", "error");
    } finally {
      setBusyId(null);
    }
  };

  const messageConnection = async (userId: string) => {
    setBusyId(userId);
    try {
      const room = await apiFetch<{ id: string }>(`/chat/dm/${userId}`, { method: "POST" });
      router.push(`/chat/${room.id}`);
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't start a conversation.", "error");
    } finally {
      setBusyId(null);
    }
  };

  const removeConnection = async (userId: string) => {
    setBusyId(userId);
    try {
      await apiFetch(`/follows/connections/${userId}`, { method: "DELETE" });
      toast.show("Connection removed.", "success");
      loadConnections();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't remove connection.", "error");
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <div className="mx-auto max-w-2xl px-6 py-16 text-fg-muted"><PageLoader size="md" /></div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to connect with other people.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  const pendingCount = incoming?.length ?? 0;

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Connections</h1>
      <p className="mt-1 text-sm text-fg-muted">
        Send a follow request to someone — once they accept, you can message each other.
      </p>

      <div className="mt-6 flex gap-1 border-b border-ink-800">
        {[
          { key: "connections" as const, label: "Connections" },
          { key: "requests" as const, label: `Requests${pendingCount ? ` (${pendingCount})` : ""}` },
          { key: "find" as const, label: "Find people" },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-t-lg px-3 py-2 text-sm font-medium transition-colors ${
              tab === t.key ? "border-b-2 border-brand-600 text-fg dark:border-brand-400" : "text-fg-muted hover:text-fg"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "connections" && (
        <div className="mt-6 space-y-2">
          {connections === null && <p className="text-sm text-fg-subtle"><PageLoader size="sm" /></p>}
          {connections !== null && connections.length === 0 && (
            <p className="text-sm text-fg-subtle">No connections yet — find people to follow.</p>
          )}
          {connections?.map((c) => (
            <div key={c.user_id} className="card flex items-center gap-3 !p-3">
              <Avatar name={c.full_name} url={c.avatar_url} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-fg">{c.full_name}</p>
                <p className="truncate text-xs text-fg-subtle">
                  {c.public_handle ? `@${c.public_handle} · ` : ""}Connected {formatRelative(c.connected_since)}
                </p>
              </div>
              <button onClick={() => messageConnection(c.user_id)} disabled={busyId === c.user_id} className="btn-primary !px-3 !py-1.5 text-xs">
                Message
              </button>
              <button onClick={() => removeConnection(c.user_id)} disabled={busyId === c.user_id} className="btn-secondary !px-3 !py-1.5 text-xs">
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      {tab === "requests" && (
        <div className="mt-6 space-y-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">Incoming</p>
            <div className="mt-2 space-y-2">
              {incoming !== null && incoming.length === 0 && <p className="text-sm text-fg-subtle">No pending requests.</p>}
              {incoming?.map((r) => (
                <div key={r.id} className="card flex items-center gap-3 !p-3">
                  <Avatar name={r.requester_name} url={null} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-fg">{r.requester_name}</p>
                    <p className="truncate text-xs text-fg-subtle">
                      {r.requester_handle ? `@${r.requester_handle} · ` : ""}Requested {formatRelative(r.created_at)}
                    </p>
                  </div>
                  <button onClick={() => respond(r.id, "accept")} disabled={busyId === r.id} className="btn-primary !px-3 !py-1.5 text-xs">Accept</button>
                  <button onClick={() => respond(r.id, "decline")} disabled={busyId === r.id} className="btn-secondary !px-3 !py-1.5 text-xs">Decline</button>
                </div>
              ))}
            </div>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">Sent</p>
            <div className="mt-2 space-y-2">
              {outgoing !== null && outgoing.length === 0 && <p className="text-sm text-fg-subtle">No pending sent requests.</p>}
              {outgoing?.map((r) => (
                <div key={r.id} className="card flex items-center gap-3 !p-3">
                  <Avatar name={r.target_name} url={null} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-fg">{r.target_name}</p>
                    <p className="truncate text-xs text-fg-subtle">
                      {r.target_handle ? `@${r.target_handle} · ` : ""}Sent {formatRelative(r.created_at)} &middot; waiting for response
                    </p>
                  </div>
                  <button onClick={() => cancelRequest(r.id)} disabled={busyId === r.id} className="btn-secondary !px-3 !py-1.5 text-xs">Cancel</button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === "find" && (
        <div className="mt-6">
          <div className="flex gap-2">
            <input
              className="input"
              placeholder="Search by name or @username…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search()}
            />
            <button onClick={search} disabled={searching} className="btn-primary shrink-0">{searching ? "Searching…" : "Search"}</button>
          </div>
          <div className="mt-4 space-y-2">
            {results?.map((p) => (
              <div key={p.user_id} className="card flex items-center gap-3 !p-3">
                <Avatar name={p.full_name} url={p.avatar_url} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-fg">{p.full_name}</p>
                  {p.public_handle && <p className="truncate text-xs text-fg-subtle">@{p.public_handle}</p>}
                </div>
                {p.relationship === "connected" && <span className="text-xs text-fg-subtle">Connected</span>}
                {p.relationship === "pending_outgoing" && <span className="text-xs text-fg-subtle">Requested</span>}
                {p.relationship === "pending_incoming" && <span className="text-xs text-fg-subtle">Sent you a request</span>}
                {p.relationship === "none" && (
                  <button onClick={() => sendRequest(p.user_id)} disabled={busyId === p.user_id} className="btn-primary !px-3 !py-1.5 text-xs">
                    Follow
                  </button>
                )}
              </div>
            ))}
            {results !== null && results.length === 0 && <p className="text-sm text-fg-subtle">No results.</p>}
          </div>
        </div>
      )}
    </div>
  );
}
