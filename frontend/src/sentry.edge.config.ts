// Edge runtime Sentry init — imported from src/instrumentation.ts when
// running under the Edge runtime (middleware, edge API routes). Same
// inert-unless-configured guard as the other two config files.
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_APP_ENV || "development",
    tracesSampleRate: 0,
    sendDefaultPii: false,
  });
}
