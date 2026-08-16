"use client";

import { apiFetch } from "@/lib/api";

/** VAPID public keys arrive base64url-encoded (RFC 4648 §5); the browser's
 * PushManager.subscribe() wants a raw byte buffer for applicationServerKey.
 * Keep a concrete ArrayBuffer copy so TypeScript 6's stricter DOM typings
 * don't widen the underlying buffer to ArrayBufferLike. */
function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(new ArrayBuffer(rawData.length));
  for (let i = 0; i < rawData.length; i++) outputArray[i] = rawData.charCodeAt(i);
  return outputArray;
}

export interface PushSupport {
  supported: boolean;
  permission: NotificationPermission | "unsupported";
}

/** `navigator.serviceWorker.ready` never resolves at all if no service
 * worker ever successfully registers (e.g. registration failed silently,
 * or Serwist is disabled outside production — see
 * ServiceWorkerRegister.tsx) — without a bound, a user clicking "Enable"
 * would see a spinner that never finishes and no error, with no way to
 * know anything went wrong. */
async function serviceWorkerReadyOrTimeout(timeoutMs = 8000): Promise<ServiceWorkerRegistration> {
  return Promise.race([
    navigator.serviceWorker.ready,
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error("No active service worker found — try reloading the page.")), timeoutMs)
    ),
  ]);
}

export function getPushSupport(): PushSupport {
  if (typeof window === "undefined" || !("serviceWorker" in navigator) || !("PushManager" in window)) {
    return { supported: false, permission: "unsupported" };
  }
  return { supported: true, permission: Notification.permission };
}

/** Requests notification permission (if not already decided), then
 * registers a real PushManager subscription against the browser's own push
 * service, and finally POSTs it to our backend — the exact three-step flow
 * every real Web Push integration does, no shortcuts. Throws with a
 * human-readable message on any failure (permission denied, VAPID not
 * configured server-side, etc.) so the caller can toast it. */
export async function subscribeToPush(): Promise<void> {
  const support = getPushSupport();
  if (!support.supported) throw new Error("Push notifications aren't supported in this browser.");

  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notification permission was not granted.");

  const { configured, public_key } = await apiFetch<{ configured: boolean; public_key: string | null }>(
    "/notifications/push/vapid-public-key",
    { auth: false }
  );
  if (!configured || !public_key) {
    throw new Error("Push notifications aren't configured on this server yet.");
  }

  const registration = await serviceWorkerReadyOrTimeout();
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    const applicationServerKey = urlBase64ToUint8Array(public_key);
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey,
    });
  }

  const json = subscription.toJSON();
  await apiFetch("/notifications/push/subscribe", {
    method: "POST",
    body: JSON.stringify({
      endpoint: json.endpoint,
      keys: { p256dh: json.keys?.p256dh, auth: json.keys?.auth },
      user_agent: navigator.userAgent,
    }),
  });
}
