// Server-side (Node runtime) Sentry init — imported from src/instrumentation.ts.
// Same inert-unless-configured guard as instrumentation-client.ts.
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
