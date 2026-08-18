"use client";

import { useEffect, useState } from "react";

/** Weekend AI-exam slots, in IST wall-clock: Saturday & Sunday, 09:00 and 18:00. */
const SLOT_HOURS = [9, 18];
const SLOT_DAYS = [6, 0]; // Sat, Sun (JS getUTCDay on an IST-midnight instant)

function nextSlot(now: Date): { date: Date; dayName: string; timeLabel: string } {
  const istParts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const get = (t: string) => istParts.find((p) => p.type === t)?.value ?? "";
  const base = new Date(`${get("year")}-${get("month")}-${get("day")}T00:00:00+05:30`);

  for (let addDays = 0; addDays < 8; addDays++) {
    const day = new Date(base.getTime() + addDays * 86400000);
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Kolkata",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(day);
    const dISO = `${parts.find((p) => p.type === "year")?.value}-${parts.find((p) => p.type === "month")?.value}-${parts.find((p) => p.type === "day")?.value}`;
    if (!SLOT_DAYS.includes(new Date(day).getUTCDay())) continue;
    for (const h of SLOT_HOURS) {
      const target = new Date(`${dISO}T${String(h).padStart(2, "0")}:00:00+05:30`);
      if (target.getTime() > now.getTime()) {
        return {
          date: target,
          dayName: target.toLocaleDateString("en-US", { timeZone: "Asia/Kolkata", weekday: "long" }),
          timeLabel: h < 12 ? "09:00 IST" : "18:00 IST",
        };
      }
    }
  }
  return { date: new Date(now.getTime() + 86400000), dayName: "This weekend", timeLabel: "IST" };
}

function countdown(ms: number): string {
  const t = Math.max(0, Math.floor(ms / 1000));
  const d = Math.floor(t / 86400);
  const h = Math.floor((t % 86400) / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = t % 60;
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  return `${m}m ${s}s`;
}

/** A small, real scheduling widget for the hero: when the next AI-conducted
 *  exam opens, and the fixed rules that govern it. No decoration — the times
 *  are the point. */
export function HeroLivePanel() {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  if (!now) {
    return <div className="card h-64 w-full" aria-hidden="true" />;
  }

  const slot = nextSlot(now);

  return (
    <div className="card p-5 sm:p-6">
      <div className="flex items-baseline justify-between border-b border-ink-700 pb-3">
        <h2 className="!text-sm font-semibold text-fg">Next exam</h2>
        <span className="text-xs text-fg-subtle">AI-conducted</span>
      </div>

      <div className="pt-4">
        <div className="text-2xl font-semibold text-fg">{slot.dayName}</div>
        <div className="mt-0.5 text-sm text-fg-muted">
          {slot.timeLabel} · opens in <span className="font-medium tabular-nums text-fg">{countdown(slot.date.getTime() - now.getTime())}</span>
        </div>
      </div>

      <dl className="mt-5 divide-y divide-ink-700 text-sm">
        <Row k="When" v="Saturday & Sunday · 09:00 and 18:00 IST" />
        <Row k="During" v="Fullscreen, proctored, one attempt" />
        <Row k="Grading" v="On the server, the moment you submit" />
        <Row k="Certificate" v="Top 3 scorers, issued automatically" />
      </dl>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-6 py-2.5">
      <dt className="shrink-0 text-fg-subtle">{k}</dt>
      <dd className="text-right text-fg-muted">{v}</dd>
    </div>
  );
}

export default HeroLivePanel;
