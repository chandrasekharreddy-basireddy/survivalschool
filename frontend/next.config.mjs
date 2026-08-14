import { withSentryConfig } from "@sentry/nextjs";
import withSerwistInit from "@serwist/next";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

// Compiles src/app/sw.ts (the real service worker source, see that file's
// own comments) into public/sw.js at build time, injecting the actual
// hashed asset manifest for this build to precache. Disabled in
// development on purpose — a cached app shell is actively unhelpful while
// iterating locally (`next dev`), and Serwist recommends this.
const withSerwist = withSerwistInit({
  swSrc: "src/app/sw.ts",
  swDest: "public/sw.js",
  cacheOnNavigation: true,
  reloadOnOnline: true,
  disable: process.env.NODE_ENV === "development",
});

// withSentryConfig is always applied (it's what makes source maps upload
// possible in a real deployment), but it only actually does anything at
// build time if SENTRY_AUTH_TOKEN is set — which it isn't in this build,
// so this stays a no-op wrapper around the plain config above. Runtime
// behavior (whether errors are actually captured) is controlled
// separately by NEXT_PUBLIC_SENTRY_DSN — see src/instrumentation-client.ts.
export default withSentryConfig(withSerwist(nextConfig), {
  silent: true,
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  widenClientFileUpload: false,
  webpack: {
    treeshake: { removeDebugLogging: true },
    automaticVercelMonitors: false,
  },
});
