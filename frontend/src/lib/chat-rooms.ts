import { createContext, useContext } from "react";

export interface RoomOut {
  id: string;
  name: string;
  room_type: string;
  other_user_id: string | null;
  other_user_name: string | null;
}

// The chat layout owns the one /chat/rooms fetch for the whole /chat/*
// subtree; child pages (e.g. the room page) read from this instead of
// independently re-fetching the full list just to find their own room in
// it — that used to double both the request count and the backend work on
// every room visit. Lives outside layout.tsx because a layout/page file
// may only export the specific names Next.js's App Router recognizes
// (default, metadata, generateMetadata, ...) — an extra custom hook export
// like this one fails typed-route checking under a webpack build (Next 16
// defaults to Turbopack, which doesn't enforce this the same way, but
// production here builds with --webpack so Serwist can generate the
// service worker — see next.config.mjs).
export const ChatRoomsContext = createContext<RoomOut[] | null>(null);

export function useChatRooms(): RoomOut[] | null {
  return useContext(ChatRoomsContext);
}
