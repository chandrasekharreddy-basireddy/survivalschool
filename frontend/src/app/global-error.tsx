"use client";

// App Router's last-resort error boundary — catches errors the root
// layout itself throws, which nothing else in the tree can catch. Reports
// to Sentry when configured (captureException is a documented safe no-op
// when NEXT_PUBLIC_SENTRY_DSN was never set, matching the rest of this
// build's Sentry wiring — see src/instrumentation-client.ts).
import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";
import "./globals.css";

export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="flex min-h-screen items-center justify-center bg-ink-950 px-6 text-center">
        <div>
          <h1 className="text-2xl font-bold text-fg">Something went wrong</h1>
          <p className="mt-2 text-sm text-fg-muted">
            We hit an unexpected error. Try reloading the page — if it keeps happening, let us know.
          </p>
          <button onClick={() => window.location.reload()} className="btn-primary mt-6">
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
