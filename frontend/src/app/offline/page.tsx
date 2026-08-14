"use client";

import { useEffect, useState } from "react";

// Served by the service worker (see src/app/sw.ts's `fallbacks` config) when
// a navigation request fails with no cached page to fall back to — i.e. the
// user is genuinely offline and hasn't visited this route before. Not shown
// for API failures (those never get this treatment — see sw.ts's
// NetworkOnly matcher on /api/*), only for whole-page navigations.
export default function OfflinePage() {
  const [online, setOnline] = useState(true);

  useEffect(() => {
    setOnline(navigator.onLine);
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-lg flex-col items-center justify-center px-6 text-center">
      <p className="text-sm font-semibold uppercase tracking-widest text-brand-600 dark:text-brand-400">
        {online ? "Back online" : "Offline"}
      </p>
      <h1 className="mt-2 text-2xl font-bold text-fg">
        {online ? "You're back online" : "You're offline"}
      </h1>
      <p className="mt-2 text-sm text-fg-muted">
        {online
          ? "Your connection is back — reload to pick up where you left off."
          : "This page needs a live connection and hasn't been visited before, so it isn't available offline. Pages you've already opened will keep working."}
      </p>
      <button onClick={() => window.location.reload()} className="btn-primary mt-6">
        {online ? "Reload" : "Try again"}
      </button>
    </div>
  );
}
