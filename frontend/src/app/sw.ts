/// <reference lib="webworker" />
// The service worker source — Serwist's build step (wired in
// next.config.mjs via withSerwistInit) compiles this into public/sw.js,
// injecting the real list of hashed build assets to precache
// (self.__SW_MANIFEST). Nothing in this file is hand-maintained boilerplate
// that goes stale on the next deploy; the manifest is regenerated on every
// build.
//
// What "offline-capable" honestly means for this app: Survival School is a
// security-sensitive, personalized education platform (auth, live exam
// timers, real-time chat, server-scored quizzes) — it does NOT attempt
// offline exam-taking or background-synced writes, which would be a
// meaningfully different (and riskier) product than what exists today.
// What this DOES give a real user: the app shell (JS/CSS/fonts/icons)
// loads instantly from cache on a repeat visit even with a flaky
// connection, previously-visited pages render from cache when fully
// offline, and a real, non-generic offline page appears for anything that
// genuinely needs a live network round-trip and doesn't have one.
import { defaultCache } from "@serwist/next/worker";
import type { PrecacheEntry, SerwistGlobalConfig } from "serwist";
import { NetworkOnly, Serwist } from "serwist";

declare global {
  interface ServiceWorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}

// ServiceWorkerGlobalScope (not the more generic WorkerGlobalScope) — needed
// for the push/notificationclick handlers below, which use
// self.registration.showNotification and self.clients, both SW-specific.
declare const self: ServiceWorkerGlobalScope;

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  runtimeCaching: [
    // Never cache API calls — every read here can be per-user, permission-
    // gated, or time-sensitive (exam deadlines, chat, live scores), and
    // serving a stale cached response for those would be actively
    // misleading, not "helpfully offline." Real API failures surface as
    // real errors, exactly like on a desktop browser with no service
    // worker at all.
    {
      matcher: ({ url }) => url.pathname.startsWith("/api/"),
      handler: new NetworkOnly(),
    },
    ...defaultCache,
  ],
  fallbacks: {
    entries: [
      {
        url: "/offline",
        matcher: ({ request }) => request.destination === "document",
      },
    ],
  },
});

serwist.addEventListeners();

// --- Web Push (RFC 8030) ---
// Serwist's addEventListeners() wires 'fetch'/'install'/'activate' for
// caching; it does not touch 'push' or 'notificationclick', so those are
// registered directly here. This is real, standard Push API/Notifications
// API code — the backend (app/services/push_service.py) sends the payload
// this 'push' handler receives via pywebpush + this app's own VAPID keys,
// no third-party push SDK involved on either side.
self.addEventListener("push", (event) => {
  let data: { title?: string; body?: string; url?: string } = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "Survival School", body: event.data ? event.data.text() : "" };
  }

  const title = data.title || "Survival School";
  const options: NotificationOptions = {
    body: data.body || "",
    icon: "/icon.svg",
    badge: "/icon.svg",
    data: { url: data.url || "/notifications" },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/notifications";

  event.waitUntil(
    (async () => {
      const allClients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      const origin = self.location.origin;
      const existing = allClients.find((c) => "focus" in c && new URL(c.url).origin === origin);
      if (existing && "focus" in existing) {
        await (existing as WindowClient).focus();
        if ("navigate" in existing) {
          await (existing as WindowClient).navigate(targetUrl).catch(() => {});
        }
        return;
      }
      await self.clients.openWindow(targetUrl);
    })()
  );
});
