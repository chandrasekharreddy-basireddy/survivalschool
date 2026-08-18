"use client";

import { useEffect } from "react";

// Shared route-level error boundary UI (Next.js App Router error.tsx). Gives the
// user a real message and a Retry button (Next's `reset()`), rather than letting
// a failed/hung data fetch bubble to the full-page root error boundary. Per-route
// error.tsx files render this with the props Next passes them.
export function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Surface to the console (and Sentry, if configured) so a broken segment is
    // observable and not silently swallowed by the boundary.
    console.error(error);
  }, [error]);

  return (
    <div className="page-frame" role="alert">
      <div className="mx-auto max-w-md space-y-4 py-16 text-center">
        <h1 className="text-xl font-semibold text-fg">Something went wrong</h1>
        <p className="text-fg-muted">
          We couldn&apos;t load this page. This is usually temporary — please try again.
        </p>
        <button
          type="button"
          onClick={reset}
          className="inline-flex items-center rounded-lg bg-brand-600 px-4 py-2 font-medium text-white hover:bg-brand-700"
        >
          Try again
        </button>
      </div>
    </div>
  );
}

export default RouteError;
