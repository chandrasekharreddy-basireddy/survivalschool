// Single shared implementation — previously duplicated (byte-identical) in
// chat/layout.tsx and chat/[roomId]/page.tsx, with a third, inconsistent
// single-letter variant in follows/page.tsx, so the same user's avatar
// showed different initials on different pages.
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase() || "?";
}
