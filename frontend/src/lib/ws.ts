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
