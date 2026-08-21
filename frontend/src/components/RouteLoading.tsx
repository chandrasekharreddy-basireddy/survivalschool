import { PageLoader } from "@/components/PageLoader";

// Shared route-level loading fallback (Next.js App Router loading.tsx). Renders
// a lightweight skeleton instead of a blank screen while a segment's data is
// being fetched. Per-route loading.tsx files re-export this. Uses the shared
// `.skeleton` shimmer utility from globals.css, plus the app's rounded
// three-colour spinner as the immediate, unmissable "something's happening"
// cue while the skeleton fills in behind it.
export function RouteLoading() {
  return (
    <div className="page-frame" role="status" aria-live="polite" aria-busy="true">
      <PageLoader size="md" className="mb-6" />
      <div className="space-y-4" aria-hidden="true">
        <div className="skeleton h-8 w-1/3 rounded" />
        <div className="skeleton h-4 w-2/3 rounded" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skeleton h-32 rounded-xl" />
          ))}
        </div>
      </div>
    </div>
  );
}

export default RouteLoading;
