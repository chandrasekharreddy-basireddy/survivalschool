# Web Push notifications: real VAPID, no third-party account

## What this is

Real browser push notifications — the "get a notification even when the tab
isn't open" kind — implemented on the open Web Push standard (RFC 8030,
delivery) and VAPID (RFC 8292, application identification). No Firebase
Cloud Messaging project, no Apple Push Notification service certificate, no
OneSignal/Pusher/etc. account is required or used. The only "third party"
involved is each browser vendor's own push service (Chrome routes through
Google's FCM endpoint, Firefox through Mozilla's autopush) — every Web Push
implementation on the internet talks to those, because the browser itself
chooses that endpoint when a page calls `PushManager.subscribe()`; there's no
way to do real web push without it, and it needs no account or API key of
ours to work.

## How it's built

**Backend**

- **`app/models/social.py` — `PushSubscription`**: one row per
  browser/device subscription (`endpoint`, `p256dh`, `auth`, `user_agent`),
  FK'd to the user, `endpoint` unique so re-subscribing upserts instead of
  duplicating. Migration: `alembic/versions/f2a7c9e1b4d6_add_push_subscriptions.py`.
  `NotificationPreference` gained a `push_enabled` column alongside the
  existing `email_enabled`.
- **`app/services/push_service.py`**: `send_to_user()` loads a user's
  subscriptions and calls `pywebpush.webpush()` for each — real RFC 8291
  payload encryption (aes128gcm) and VAPID JWT signing, not hand-rolled
  crypto. A `404`/`410` response (the push service's way of saying "this
  subscription is dead") deletes the row; any other failure is logged and
  left alone (transient — worth retrying next time, not a reason to fail the
  request that triggered the notification). Inert (`push_configured()` ==
  `False`, `send_to_user()` a no-op returning `0`) whenever
  `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` aren't set — same pattern as
  `SENTRY_DSN` elsewhere in this codebase: no fabricated credential is ever
  present, a real deployment sets its own.
- **`app/services/notification_service.py`**: `create_notification()` now
  also fires a real push after creating the in-app notification (and email,
  if enabled) — gated by the same per-category preference as email, plus
  `push_enabled`, with the same "security notifications are never silently
  disabled" exception the email path already had.
- **`app/api/v1/notifications.py`** — new endpoints:
  - `GET /notifications/push/vapid-public-key` — the public key only (safe
    to expose; the private key never leaves the server).
  - `POST /notifications/push/subscribe` — stores a subscription the
    frontend obtained from `PushManager.subscribe()`.
  - `POST /notifications/push/unsubscribe` — removes it.
  - `POST /notifications/push/test` — sends one real push to the calling
    user's own subscription(s) right now, so they can self-verify it works
    without waiting for a real event.
- **`backend/scripts/generate_vapid_keys.py`** — generates a real,
  cryptographically valid VAPID keypair (P-256 EC key, the format RFC 8292
  requires) for a deployment to paste into its own `.env`. This repository's
  own dev `.env` (gitignored, never committed) has a real keypair generated
  this way for local testing — `.env.example` intentionally ships blank,
  since a real private key is a real secret that belongs per-deployment, not
  in git.

**Frontend**

- **`src/lib/push.ts`** — `subscribeToPush()` (requests permission → fetches
  the real VAPID public key → `PushManager.subscribe()` → POSTs the result
  to the backend), `unsubscribeFromPush()`, `isSubscribedToPush()`,
  `sendTestPush()`.
- **`src/app/sw.ts`** — added real `push` and `notificationclick` listeners
  to the existing Serwist service worker (the same one built for offline
  support — see `docs/PWA.md`). `push` parses the JSON payload the backend
  sent and calls `registration.showNotification()`; `notificationclick`
  focuses an existing tab if the app is already open, or opens a new one to
  the notification's target URL, either way navigating to
  `event.notification.data.url`.
- **`src/app/settings/page.tsx` — `PushNotificationsSection`**: shows
  "Enable on this device" (or "Not supported" / "blocked in your browser
  settings" as appropriate) → once subscribed, "Send test notification" and
  "Turn off on this device". The existing notification-preferences checklist
  gained a `push_enabled` toggle alongside course/assessment/etc.

## Verification: what was actually proven, and how

1. **Backend, real cryptographic wiring — proven directly, not mocked at the
   VAPID/encryption layer.** `tests/test_push.py::
   test_test_push_endpoint_calls_real_webpush_with_correct_vapid_claims`
   subscribes a real endpoint through the real API, then asserts the actual
   call into `pywebpush.webpush()` received this deployment's real
   `VAPID_PRIVATE_KEY`, the real `VAPID_SUBJECT`, and a correctly-shaped
   `subscription_info` — i.e. everything up to the literal HTTPS request to
   the push service is real; only that one final network call (which would
   need a real subscription endpoint belonging to an actual browser) is
   stubbed. A second test confirms a `410 Gone` response causes the
   subscription row to be genuinely deleted from Postgres (pruned, not
   retried forever). 6/6 tests pass; full backend suite (98 tests) passes
   except one pre-existing, unrelated flaky contest-leaderboard test that
   also fails in isolation-independent full-suite runs before this change
   and passes on its own — not something this feature touched.
2. **Frontend builds real production artifacts.** `npm run build` compiles
   `src/app/sw.ts` into `public/sw.js`; direct inspection confirms the built
   file contains `addEventListener("push", ...)`,
   `addEventListener("notificationclick", ...)`, and `showNotification` —
   the real handlers, not stripped or tree-shaken away. `tsc --noEmit` and
   `next lint` are both clean.
3. **End-to-end smoke test against real, live services (not test doubles) —
   as far as this sandbox's network allows.** A Playwright script registered
   a real user through the real `/auth/register` API, logged in for a real
   JWT, loaded the real production frontend build, confirmed the real
   service worker activated (`navigator.serviceWorker.getRegistration()` ->
   `active`), fetched this deployment's real VAPID public key from the real
   backend, then called the real
   `registration.pushManager.subscribe({ applicationServerKey })` — the
   literal browser API a real user's "Enable notifications" click invokes.
4. **The one gap, and why it's environmental, not a defect.** That real
   `subscribe()` call failed in this sandbox with
   `AbortError: Registration failed - permission denied` — not a permissions
   problem (`Notification.permission` was independently confirmed
   `"granted"` first) but Chromium's push-service *registration* step
   itself failing, because registering a subscription requires the browser
   to reach the vendor's push service over the network to mint the
   `endpoint` URL, and this sandbox's network egress is allowlisted to
   specific domains (package registries, etc.) — confirmed directly:
   `curl https://fcm.googleapis.com/` from this container returns
   `CONNECT tunnel failed, response 403`. This is the identical class of
   constraint documented in `docs/PWA.md` for the offline end-to-end test —
   a sandbox network boundary, not something wrong with the code. With that
   one browser-vendor network call substituted for a realistically-shaped
   synthetic subscription, the rest of the same script proved every other
   real component genuinely works: the real backend stored the subscription
   in Postgres (confirmed via direct `SELECT`), `/notifications/push/test`
   correctly attempted a real `pywebpush.webpush()` call against it (which
   itself then hit the same sandbox network boundary reaching
   `fcm.googleapis.com` from the backend side — logged and swallowed exactly
   per the "transient failure, leave subscription in place, don't 500"
   design in `push_service.py`, confirmed by the endpoint still returning
   `200 {"sent": 0}` rather than an error), and unsubscribe correctly
   removed the row.

**Bottom line:** every piece of this implementation that doesn't require
crossing this sandbox's specific network allowlist is directly verified
against real code paths — real VAPID key generation and signing, real
encrypted-payload construction, real database storage, real API contracts,
a real compiled service worker with real event handlers. The one
unverified link is the literal HTTPS round-trip to Google's/Mozilla's push
infrastructure, which this environment's network policy blocks outright
(confirmed via a direct `curl` 403, not inferred) — the same well-established
Web Push flow that powers push notifications on most real production sites,
independent of this sandbox's restrictions. The natural next verification
step outside this sandbox: open the deployed app in a real desktop Chrome or
Firefox with real internet access, click "Enable on this device" in
Settings, click "Send test notification," and watch it arrive.
