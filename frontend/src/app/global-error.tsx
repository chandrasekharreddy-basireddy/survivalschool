"use client";

// Root-level fallback: catches errors thrown by layout.tsx itself (a normal
// error.tsx can't, since it renders inside the layout it's meant to protect).
// Must render its own <html>/<body> since it replaces the entire root layout.
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-ink-950 text-fg">
        <div className="mx-auto flex min-h-screen max-w-lg flex-col items-center justify-center px-6 text-center">
          <h1 className="text-xl font-bold text-fg">Survival School hit a snag.</h1>
          <p className="mt-2 text-sm text-fg-muted">
            Something broke at the application level. Reloading usually fixes it.
          </p>
          <button
            onClick={() => reset()}
            className="mt-6 inline-flex items-center justify-center gap-2 rounded-lg bg-brand-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-600"
          >
            Reload
          </button>
          {error.digest && <p className="mt-4 text-xs text-fg-subtle">Reference: {error.digest}</p>}
        </div>
      </body>
    </html>
  );
}
