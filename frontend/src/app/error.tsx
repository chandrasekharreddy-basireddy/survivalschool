"use client";

import { useEffect } from "react";

export default function ErrorBoundary({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("Unhandled page error:", error);
  }, [error]);

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-lg flex-col items-center justify-center px-6 text-center">
      <h1 className="text-xl font-bold text-fg">Something went wrong.</h1>
      <p className="mt-2 text-sm text-fg-muted">
        This page hit an unexpected error. It's been logged — try again, or head back to the dashboard.
      </p>
      <div className="mt-6 flex gap-3">
        <button onClick={() => reset()} className="btn-primary">Try again</button>
        <a href="/dashboard" className="btn-secondary">Go to dashboard</a>
      </div>
      {error.digest && <p className="mt-4 text-xs text-fg-subtle">Reference: {error.digest}</p>}
    </div>
  );
}
