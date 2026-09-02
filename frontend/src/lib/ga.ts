"use client";

// Thin wrapper around gtag.js — entirely optional. Every function here is a
// safe no-op when NEXT_PUBLIC_GA_MEASUREMENT_ID isn't set (the default, same
// convention this repo already uses for NEXT_PUBLIC_SENTRY_DSN) or when the
// visitor has Do Not Track enabled, so nothing needs to check "is GA on?"
// before calling these.

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

export const GA_MEASUREMENT_ID = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID || "";

export function gaEnabled(): boolean {
  if (!GA_MEASUREMENT_ID || typeof window === "undefined") return false;
  // navigator.doNotTrack is "1" in most browsers; old IE used
  // window.doNotTrack. Any other value (including "unspecified"/null) means
  // no preference was expressed, which we treat as consent to track.
  const dnt = navigator.doNotTrack || (window as unknown as { doNotTrack?: string }).doNotTrack;
  return dnt !== "1" && dnt !== "yes";
}

export function trackPageView(path: string) {
  if (!gaEnabled() || typeof window.gtag !== "function") return;
  window.gtag("event", "page_view", { page_path: path });
}

export function trackGaEvent(name: string, params: Record<string, unknown> = {}) {
  if (!gaEnabled() || typeof window.gtag !== "function") return;
  window.gtag("event", name, params);
}
