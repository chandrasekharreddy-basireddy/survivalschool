"use client";

import { useEffect } from "react";

// Registers the Serwist-generated service worker (public/sw.js, built from
// src/app/sw.ts). Next.js doesn't auto-register a service worker just
// because one exists on disk — this is the one bit of client wiring that
// makes it actually load. Silently no-ops in any browser/context without
// serviceWorker support (older Safari versions, some in-app webviews)
// rather than throwing.
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // Registration can fail in dev (Serwist disables SW generation
        // outside production, per next.config.mjs) or in browsers that
        // block it — never surface this to the user, offline support
        // degrading to "no offline support" is not a user-facing error.
      });
    });
  }, []);

  return null;
}
