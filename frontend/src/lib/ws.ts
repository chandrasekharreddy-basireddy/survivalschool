"use client";

// Thin wrapper around the native WebSocket for the chat room socket
// (backend: app/websockets/chat.py, mounted at /ws/chat/{room_id}). Handles
// the token-in-query-param handshake (browsers can't set custom headers on a
// WS upgrade request, so the access token travels as ?token=), JSON framing,
// and automatic reconnect with capped exponential backoff so a dropped wifi
// connection doesn't just leave the chat room permanently disconnected.
//
// Message history is never solely reliant on this socket — see the backend
// docstring — so callers should always hydrate from GET
// /chat/rooms/{id}/messages first and treat this purely as a live-append feed.

const WS_BASE = process.env.NEXT_PUBLIC_WS_BASE_URL || "ws://localhost:8000";

export type ChatEvent =
  | { event: "chat.message"; id: string; room_id: string; sender_id: string | null; body: string; created_at: string }
  | { event: "chat.typing"; user_id: string }
  | { event: "chat.read"; user_id: string; message_id: string }
  | { event: "presence.updated"; user_id: string; status: "online" | "offline" };

type Listener = (evt: ChatEvent) => void;

export class ChatSocket {
  private ws: WebSocket | null = null;
  private roomId: string;
  private token: string;
  private listeners = new Set<Listener>();
  private closedByUser = false;
  private attempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(roomId: string, token: string) {
    this.roomId = roomId;
    this.token = token;
  }

  connect() {
    this.closedByUser = false;
    const url = `${WS_BASE}/ws/chat/${this.roomId}?token=${encodeURIComponent(this.token)}`;
    this.ws = new WebSocket(url);
    this.ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as ChatEvent;
        this.listeners.forEach((fn) => fn(data));
      } catch {
        /* ignore malformed frames */
      }
    };
    this.ws.onopen = () => {
      this.attempt = 0;
    };
    this.ws.onclose = () => {
      if (this.closedByUser) return;
      const delay = Math.min(1000 * 2 ** this.attempt, 15000);
      this.attempt += 1;
      this.reconnectTimer = setTimeout(() => this.connect(), delay);
    };
  }

  on(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  sendMessage(body: string) {
    this.ws?.readyState === WebSocket.OPEN && this.ws.send(JSON.stringify({ event: "chat.message", body }));
  }

  sendTyping() {
    this.ws?.readyState === WebSocket.OPEN && this.ws.send(JSON.stringify({ event: "chat.typing" }));
  }

  sendRead(messageId: string) {
    this.ws?.readyState === WebSocket.OPEN && this.ws.send(JSON.stringify({ event: "chat.read", message_id: messageId }));
  }

  close() {
    this.closedByUser = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }
}

// Thin wrapper around the native WebSocket for the elimination battle socket
// (backend: app/websockets/elimination.py, mounted at /ws/elimination/{battle_id}).
// Read-only from the client's side — this only receives push events, all
// actions still go through the REST endpoints. Same token-in-query-param
// handshake and automatic reconnect as ChatSocket above; a battle can run
// for many minutes across many rounds, so a dropped connection here used to
// mean every event after the drop (round released, someone eliminated, the
// battle finishing) was silently missed until the participant manually
// refreshed the page.
export type EliminationEvent =
  | { event: "battle.started"; battle_id: string }
  | { event: "battle.round_released"; battle_id: string; round_number: number; question: unknown; deadline_at: string }
  | { event: "battle.answer_result"; battle_id: string; user_id: string; round_number: number; is_correct: boolean }
  | { event: "battle.round_resolved"; battle_id: string; round_number: number; eliminated_user_ids: string[]; survivors_remaining: number }
  | { event: "battle.completed"; battle_id: string; winner_user_id: string | null }
  | { event: "battle.cancelled"; battle_id: string }
  | { event: "battle.participant_eliminated"; battle_id: string; user_id: string; round_number: number; reason: string };

type EliminationListener = (evt: EliminationEvent) => void;

export class EliminationSocket {
  private ws: WebSocket | null = null;
  private battleId: string;
  private token: string;
  private listeners = new Set<EliminationListener>();
  private openListeners = new Set<() => void>();
  private closedByUser = false;
  private attempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private everConnected = false;

  constructor(battleId: string, token: string) {
    this.battleId = battleId;
    this.token = token;
  }

  connect() {
    this.closedByUser = false;
    const url = `${WS_BASE}/ws/elimination/${this.battleId}?token=${encodeURIComponent(this.token)}`;
    this.ws = new WebSocket(url);
    this.ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as EliminationEvent;
        this.listeners.forEach((fn) => fn(data));
      } catch {
        /* ignore malformed frames */
      }
    };
    this.ws.onopen = () => {
      this.attempt = 0;
      // Skip the very first (normal) connect — callers already do their
      // own initial REST hydration. This fires only for a RE-open after a
      // drop, when events broadcast while disconnected would otherwise be
      // silently missed, so the reconnect needs to trigger a fresh re-sync.
      if (this.everConnected) this.openListeners.forEach((fn) => fn());
      this.everConnected = true;
    };
    this.ws.onclose = () => {
      if (this.closedByUser) return;
      const delay = Math.min(1000 * 2 ** this.attempt, 15000);
      this.attempt += 1;
      this.reconnectTimer = setTimeout(() => this.connect(), delay);
    };
  }

  on(fn: EliminationListener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  /** Fires on every reconnect after a drop (not the initial connect). */
  onReconnect(fn: () => void): () => void {
    this.openListeners.add(fn);
    return () => this.openListeners.delete(fn);
  }

  close() {
    this.closedByUser = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }
}
