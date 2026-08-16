"use client";

// Thin wrapper around the native WebSocket for the chat room socket.
// Browser auth now rides the HttpOnly ss_access_token cookie automatically;
// no JWT is placed in the URL. The backend still accepts a legacy query token
// temporarily for non-browser clients during migration.
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
  private listeners = new Set<Listener>();
  private closedByUser = false;
  private attempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(roomId: string) {
    this.roomId = roomId;
  }

  connect() {
    this.closedByUser = false;
    const url = `${WS_BASE}/ws/chat/${this.roomId}`;
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
