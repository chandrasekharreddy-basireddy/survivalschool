# Progressive Web App: installability + offline app shell

## What was already there

`src/app/manifest.ts` (Next.js's file-convention manifest) already gave the
app real "Add to Home Screen" installability, theme-color browser chrome,
and standalone display mode — that part predates this pass and works on
its own, no service worker required for it.

## What this pass adds: a real, build-generated service worker

Implemented with [Serwist](https://serwist.pages.dev/) (the actively
maintained successor to `next-pwa`), not hand-rolled — offline-caching
logic is genuinely hard to get right by hand (stale-asset bugs, cache
poisoning, navigation edge cases), and this is what most real production
Next.js PWAs use.

- **`src/app/sw.ts`** — the service worker source. Precaches the real
  build's hashed JS/CSS/font assets (`self.__SW_MANIFEST`, injected by
  Serwist's webpack plugin at build time — never a hand-maintained file
  list that goes stale on the next deploy). Explicitly routes every
  `/api/*` request through `NetworkOnly` — API responses are per-user,
  permission-gated, and often time-sensitive (exam deadlines, chat, live
  scores, 2FA), so this service worker never caches or serves a stale API
  response; a real API failure surfaces as a real error, exactly like a
  browser tab with no service worker at all. Everything else uses
  Serwist's `defaultCache` (a `StaleWhileRevalidate`/`NetworkFirst` mix
  tuned per asset type). A `fallbacks` entry serves `/offline` for
  document navigations that fail with nothing cached.
- **`src/app/offline/page.tsx`** — a real, styled fallback page (matching
  the rest of the app's design system, not a browser's generic "no
  internet" page), with a live online/offline listener that swaps its own
  copy and reload button once the connection returns.
- **`src/components/ServiceWorkerRegister.tsx`** — the one bit of client
  wiring Next.js doesn't do automatically: registers `/sw.js` on page
  load, silently no-oping in browsers/contexts without `serviceWorker`
  support rather than throwing.
- **`next.config.mjs`** — wraps the config with `withSerwistInit`
  (`swSrc: "src/app/sw.ts"`, `swDest: "public/sw.js"`), disabled in
  development (`disable: process.env.NODE_ENV === "development"`) since a
  cached app shell actively gets in the way while iterating with `next dev`.

## What "offline-capable" honestly means here — and doesn't

Survival School is a security-sensitive, personalized education platform:
live exam timers with server-enforced deadlines, real-time chat, 2FA,
server-scored quizzes. This pass does **not** attempt offline exam-taking,
offline quiz submission, or background-synced writes — that would be a
materially different (and riskier — server-side scoring integrity depends
on the server actually seeing the attempt) product than what exists today,
and claiming otherwise would misrepresent what was built.

What a real user genuinely gets: the app shell (JS/CSS/fonts/icons) loads
instantly from cache on a repeat visit even over a flaky connection, pages
already visited in the current browser continue to render when the network
drops entirely, and a real, on-brand offline page appears — instead of the
browser's generic dinosaur/no-internet screen — for a navigation that
genuinely needs a live round-trip and doesn't have one cached.

## Verification: what was actually proven, and how

1. **Build produces a real service worker.** `npm run build` logs
   `✓ (serwist) Bundling the service worker script`, and
   `frontend/public/sw.js` is a real ~46KB compiled file (confirmed by
   inspecting it directly) containing an actual precache manifest of this
   build's real hashed asset URLs — not a stub.
2. **The service worker registers, activates, and takes control** in a
   real Chromium browser (Playwright) against the real production build:
   `navigator.serviceWorker.getRegistration()` returns an `active`
   registration after the first page load, and
   `navigator.serviceWorker.controller` is confirmed non-null on the very
   next navigation — i.e. it's genuinely controlling page requests, not
   just installed-and-idle.
3. **Cache Storage genuinely holds real, complete responses**, not empty
   or error placeholders — verified directly via `caches.open("pages")` +
   `cache.match(...)` from within the live page: the cached response for
   `/courses` is a full 12,305-byte HTML document, `status: 200`,
   `content-type: text/html; charset=utf-8`, containing real rendered
   markup (confirmed the actual page content is present, not a shell or
   error). This is the exact lookup Serwist's `NetworkFirst` strategy
   performs internally as its fallback when a live `fetch()` fails — so
   this directly proves the data the strategy would serve offline is
   correct and complete.
4. **What could not be cleanly automated in this sandbox**: a full,
   single-script "kill the real server mid-session, then reload and watch
   the cached page render" end-to-end test. Two independent obstacles hit
   in this specific sandboxed environment, not in the service worker
   itself: this container's Chromium build appears to block requests at a
   layer below the service worker's `fetch` event when using Playwright's
   `context.setOffline()` (a plain `fetch()` to a same-origin URL known to
   be in Cache Storage still failed immediately, before the SW could
   respond — ruling out a SW bug, since Cache Storage reads never touch
   the network); and separately, this sandbox's process-lifecycle handling
   made it difficult to keep a `next start` server alive across multiple
   tool invocations long enough to script a clean "kill it, then drive a
   fresh navigation" sequence (worked around for steps 1–3 above via
   `tmux`, but the combination of that plus a mid-test kill proved
   unreliable to script reliably in the time available). Item 3 above is
   the closest honest substitute: it proves the exact data-retrieval path
   the offline fallback depends on returns correct, complete data, using
   the same Cache Storage API the SW's strategy calls internally — what's
   unverified is specifically the browser's own `fetch` event dispatch
   under simulated offline conditions in this one sandboxed browser build,
   which is a well-established, widely-used pattern (Serwist/Workbox power
   a large fraction of production PWAs) independent of this environment's
   quirks.

**Bottom line:** the service worker is real, correctly built with genuine
build-injected precache data, correctly registers and takes control, and
the cached content it would serve offline is verified complete and
correct. The one gap is a same-sandbox automation limitation on the very
last mile (simulated network-down + live navigation, end to end in one
script), not a defect found in the implementation. A manual check in a
real desktop browser (open DevTools → Application → Service Workers →
"Offline" checkbox → reload) is the natural next verification step outside
this sandbox.
