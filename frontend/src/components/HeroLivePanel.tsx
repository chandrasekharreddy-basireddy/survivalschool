"use client";

import { useEffect, useState } from "react";

/** Weekend AI-exam slots, in IST wall-clock: Saturday & Sunday, 09:00 and 18:00. */
const SLOT_HOURS = [9, 18];
const SLOT_DAYS = [6, 0]; // Sat, Sun (JS getDay)

/** Returns the next weekend-exam slot as a real Date (UTC instant). IST is a
 *  fixed +05:30 with no DST, so we can build the instant from an ISO string
 *  with an explicit offset once we know the calendar date in IST. */
function nextSlot(now: Date): { date: Date; label: string } {
  const istParts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const get = (t: string) => istParts.find((p) => p.type === t)?.value ?? "";
  const baseISO = `${get("year")}-${get("month")}-${get("day")}`;
  const base = new Date(`${baseISO}T00:00:00+05:30`);

  for (let addDays = 0; addDays < 8; addDays++) {
    const day = new Date(base.getTime() + addDays * 86400000);
    const iso = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Kolkata",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      weekday: "short",
    }).formatToParts(day);
    const dow = new Date(day).getUTCDay(); // base days are IST-midnight instants
    if (!SLOT_DAYS.includes(dow)) continue;
    const dISO = `${iso.find((p) => p.type === "year")?.value}-${iso.find((p) => p.type === "month")?.value}-${iso.find((p) => p.type === "day")?.value}`;
    for (const h of SLOT_HOURS) {
      const target = new Date(`${dISO}T${String(h).padStart(2, "0")}:00:00+05:30`);
      if (target.getTime() > now.getTime()) {
        const dayName = target.toLocaleDateString("en-US", { timeZone: "Asia/Kolkata", weekday: "long" });
        const timeName = h < 12 ? "09:00 (morning)" : "18:00 (evening)";
        return { date: target, label: `${dayName} · ${timeName} IST` };
      }
    }
  }
  return { date: new Date(now.getTime() + 86400000), label: "This weekend IST" };
}

function fmt(ms: number): { d: number; h: number; m: number; s: number } {
  const total = Math.max(0, Math.floor(ms / 1000));
  return {
    d: Math.floor(total / 86400),
    h: Math.floor((total % 86400) / 3600),
    m: Math.floor((total % 3600) / 60),
    s: total % 60,
  };
}

function Unit({ value, label }: { value: number; label: string }) {
  return (
    <div className="flex flex-col items-center">
      <span className="font-mono text-2xl font-bold tabular-nums text-fg sm:text-3xl">
        {String(value).padStart(2, "0")}
      </span>
      <span className="mt-0.5 text-[0.6rem] font-semibold uppercase tracking-widest text-fg-subtle">{label}</span>
    </div>
  );
}

export function HeroLivePanel() {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  if (!now) {
    return <div className="card h-[19rem] w-full animate-pulse" aria-hidden="true" />;
  }

  const slot = nextSlot(now);
  const c = fmt(slot.date.getTime() - now.getTime());

  return (
    <div className="card card-glass relative overflow-hidden p-5 sm:p-6">
      <div className="pointer-events-none absolute -right-16 -top-16 h-40 w-40 rounded-full bg-brand-500/20 blur-3xl" />
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-2 text-[0.68rem] font-bold uppercase tracking-widest text-fg-subtle">
          <span className="status-dot animate-pulse" /> System live
        </span>
        <span className="game-badge chip-brand">AI-conducted</span>
      </div>

      <p className="mt-5 text-xs font-semibold uppercase tracking-widest text-fg-subtle">Next secured exam</p>
      <p className="mt-1 text-sm font-medium text-fg-muted">{slot.label}</p>

      <div className="mt-4 grid grid-cols-4 gap-2 rounded-xl border border-ink-700 bg-ink-950/40 p-3">
        <Unit value={c.d} label="days" />
        <Unit value={c.h} label="hrs" />
        <Unit value={c.m} label="min" />
        <Unit value={c.s} label="sec" />
      </div>

      <dl className="mt-5 space-y-2.5 text-sm">
        <Row k="Schedule" v="Sat & Sun · 09:00 & 18:00 IST" />
        <Row k="Integrity" v="Fullscreen + proctored" />
        <Row k="Grading" v="Server-authoritative" />
        <Row k="Reward" v="Top 3 auto-certified" />
      </dl>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="font-mono text-[0.7rem] uppercase tracking-wider text-fg-subtle">{k}</dt>
      <dd className="text-right text-[0.82rem] font-medium text-fg-muted">{v}</dd>
    </div>
  );
}

export default HeroLivePanel;
