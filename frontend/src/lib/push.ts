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

export async function unsubscribeFromPush(): Promise<void> {
  if (!("serviceWorker" in navigator)) return;
  const registration = await serviceWorkerReadyOrTimeout();
  const subscription = await registration.pushManager.getSubscription();
  if (!subscription) return;
  const endpoint = subscription.endpoint;
  await subscription.unsubscribe();
  await apiFetch("/notifications/push/unsubscribe", { method: "POST", body: JSON.stringify({ endpoint }) });
}

export async function isSubscribedToPush(): Promise<boolean> {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) return false;
  try {
    const registration = await navigator.serviceWorker.getRegistration();
    if (!registration) return false;
    const subscription = await registration.pushManager.getSubscription();
    return !!subscription;
  } catch {
    return false;
  }
}

export async function sendTestPush(): Promise<number> {
  const res = await apiFetch<{ sent: number }>("/notifications/push/test", { method: "POST" });
  return res.sent;
}
