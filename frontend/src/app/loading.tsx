import RouteLoading from "@/components/RouteLoading";

// Root-level fallback: covers every route transition that doesn't already
// have its own more specific loading.tsx (see the per-route ones alongside
// this file's siblings) — Next.js falls back up the tree to the nearest
// loading.tsx, so this is the safety net for the rest.
export default function Loading() {
  return <RouteLoading />;
}
