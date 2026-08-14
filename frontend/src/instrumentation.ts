// Next.js's own instrumentation hook (https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation) —
// register() runs once per server runtime start, before any route handles
// a request. Used here purely to load the right Sentry config for
// whichever runtime this process actually is; both configs are themselves
// inert unless NEXT_PUBLIC_SENTRY_DSN is set, so this whole file is a
// no-op in the default (no Sentry configured) case.
import * as Sentry from "@sentry/nextjs";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }
  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

// captureRequestError is a safe no-op when Sentry.init() was never called
// (no DSN configured) — same documented behavior as the backend's
// sentry_sdk.capture_exception, see backend/app/core/exceptions.py.
export const onRequestError = Sentry.captureRequestError;
