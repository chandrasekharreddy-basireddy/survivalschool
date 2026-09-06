"use client";

import { useEffect, useRef, useState } from "react";

function format(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}

/** A sticky, always-visible countdown to the student's personal attempt
 * deadline -- the exam UI previously only printed the deadline as static
 * text once, so there was no visible pressure/awareness of time running out
 * while answering. Fires onExpire exactly once when it reaches zero. */
export function AttemptTimer({ deadline, onExpire }: { deadline: string; onExpire: () => void }) {
  const [remainingMs, setRemainingMs] = useState<number | null>(null);
  const expiredRef = useRef(false);

  useEffect(() => {
    const deadlineMs = new Date(deadline).getTime();
    const tick = () => {
      const remaining = deadlineMs - Date.now();
      setRemainingMs(remaining);
      if (remaining <= 0 && !expiredRef.current) {
        expiredRef.current = true;
        onExpire();
      }
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onExpire is fired at most once per mount; re-subscribing on its identity would risk double-firing
  }, [deadline]);

  if (remainingMs === null) return null;
  const urgent = remainingMs < 5 * 60 * 1000;

  return (
    <div
      className={`sticky top-0 z-30 -mx-6 flex items-center justify-center gap-2 px-6 py-2 text-sm font-semibold backdrop-blur ${
        urgent ? "bg-red-500/10 text-red-700 dark:text-red-400" : "bg-bg-subtle/90 text-fg"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${urgent ? "bg-red-500 animate-pulse" : "bg-emerald-500"}`} />
      Time remaining: <span className="font-mono tabular-nums">{format(remainingMs)}</span>
    </div>
  );
}
