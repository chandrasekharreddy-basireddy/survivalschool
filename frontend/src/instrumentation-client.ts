// Client-side Sentry init. Deliberately inert unless a real
// NEXT_PUBLIC_SENTRY_DSN is set — this build has no real Sentry
// account/DSN, and fabricating one would violate the "no fake
// credentials" standard for this project. See docs/OBSERVABILITY.md.
//
// A Sentry DSN is not a secret (it's designed to be embedded in a public
// client bundle — write access is controlled separately by Sentry's auth
// tokens), so NEXT_PUBLIC_ exposure here is intentional and safe.
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_APP_ENV || "development",
    tracesSampleRate: 0,
    // No session replay / no PII capture by default — this is a
    // student-facing education platform; opt into replay explicitly and
    // deliberately if that's ever wanted, rather than defaulting it on.
    sendDefaultPii: false,
  });
}

// Safe no-op when Sentry.init() was never called above (no DSN configured).
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
