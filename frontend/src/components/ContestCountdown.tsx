"use client";

import { useEffect, useState } from "react";

function formatRemaining(ms: number): string {
  if (ms <= 0) return "0:00:00";
  const totalSeconds = Math.floor(ms / 1000);
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/** A simple, honest countdown to a contest's start or close — no fake
 * urgency, just the real scheduled time ticking down client-side. */
export function ContestCountdown({ startsAt, endsAt, status }: { startsAt: string; endsAt: string; status: string }) {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  if (now === null) return null;

  const starts = new Date(startsAt).getTime();
  const ends = new Date(endsAt).getTime();

  if (status === "closed" || now > ends) {
    return <span className="text-sm text-fg-subtle">This contest has ended.</span>;
  }
  if (now < starts) {
    return (
      <span className="text-sm text-fg-muted">
        Starts in <span className="font-mono font-semibold text-brand-400">{formatRemaining(starts - now)}</span>
      </span>
    );
  }
  return (
    <span className="text-sm text-fg-muted">
      Open now — closes in <span className="font-mono font-semibold text-emerald-400">{formatRemaining(ends - now)}</span>
    </span>
  );
}
