import Link from "next/link";
import type { ReactNode } from "react";
import { HeroLivePanel } from "@/components/HeroLivePanel";

const FEATURES: { title: string; desc: string; icon: ReactNode }[] = [
  {
    title: "MCQ-first courses",
    desc: "Every lesson builds toward a real assessment — not passive video watching.",
    icon: <IconBook />,
  },
  {
    title: "AI-conducted exams",
    desc: "Fresh, AI-generated papers run every weekend — proctored, timed, and server-graded.",
    icon: <IconBolt />,
  },
  {
    title: "Live leaderboards",
    desc: "Points, streaks, and badges — all computed server-side, all real.",
    icon: <IconTrophy />,
  },
  {
    title: "Verifiable certificates",
    desc: "Every certificate carries a public verification URL and QR code.",
    icon: <IconSeal />,
  },
  {
    title: "Secured by design",
    desc: "Argon2id hashing, rotating refresh tokens, RBAC, and a Thursday registration window.",
    icon: <IconShield />,
  },
  {
    title: "Built for your campus",
    desc: "Course catalogs, timetables, and cohorts that match how your university runs.",
    icon: <IconCampus />,
  },
];

const METRICS = [
  { value: "4", label: "weekend exam slots / week" },
  { value: "100%", label: "server-graded, no client trust" },
  { value: "Top 3", label: "auto-certified each exam" },
  { value: "IST", label: "scheduled Sat & Sun, AM + PM" },
];

const STEPS = [
  { step: "01", title: "Register on Thursday", desc: "The weekly registration window opens every Thursday (IST) — enroll in the courses your university offers." },
  { step: "02", title: "Learn in short lessons", desc: "Work through bite-sized, MCQ-checkpointed lessons designed for retention." },
  { step: "03", title: "Sit the weekend exam", desc: "Take the proctored, AI-conducted exam — timed and graded the moment you submit." },
  { step: "04", title: "Earn a real certificate", desc: "Finish in the top ranks and a verifiable certificate is issued automatically." },
];

export default function LandingPage() {
  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="mx-auto grid max-w-7xl items-center gap-12 px-4 py-16 sm:px-6 sm:py-24 lg:grid-cols-[1.1fr_0.9fr] lg:gap-8 lg:py-28">
          <div className="animate-fade-in-up">
            <span className="game-badge chip-brand">
              <span className="status-dot" /> Competitive learning · built for universities
            </span>
            <h1 className="mt-6">
              Learning that feels like a game.
              <span className="mt-1 block text-gradient">Assessment that means something.</span>
            </h1>
            <p className="mt-6 max-w-xl text-lg text-fg-muted">
              Survival School turns your course material into MCQ-driven lessons and{" "}
              <strong className="font-semibold text-fg">AI-conducted weekend exams</strong> — proctored, server-graded, and
              capped with certificates your students can actually verify.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              <Link href="/register" className="btn-primary !px-6 !py-3 text-base">
                Start learning free <IconArrow />
              </Link>
              <Link href="/courses" className="btn-secondary !px-6 !py-3 text-base">
                Browse courses
              </Link>
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs font-medium text-fg-subtle">
              <span className="inline-flex items-center gap-1.5"><IconCheck /> Argon2id-secured accounts</span>
              <span className="inline-flex items-center gap-1.5"><IconCheck /> Server-authoritative timing</span>
              <span className="inline-flex items-center gap-1.5"><IconCheck /> Public certificate verification</span>
            </div>
          </div>

          <div className="animate-float-in lg:pl-6">
            <HeroLivePanel />
          </div>
        </div>
        <div className="hairline mx-auto max-w-7xl" />
      </section>

      {/* Metrics band */}
      <section className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-ink-700 bg-ink-700 lg:grid-cols-4">
          {METRICS.map((m) => (
            <div key={m.label} className="bg-ink-950 p-6 text-center sm:p-7">
              <div className="text-3xl font-extrabold tracking-tight text-fg sm:text-4xl">{m.value}</div>
              <div className="mt-1 text-xs font-medium text-fg-subtle sm:text-sm">{m.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20">
        <div className="max-w-2xl">
          <h2>Everything a modern learning platform needs</h2>
          <p className="mt-3 text-fg-muted">
            No filler dashboards. No fake stats. Every number on this platform is computed by the backend.
          </p>
        </div>
        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <article
              key={f.title}
              className="card card-hover animate-fade-in-up p-6"
              style={{ animationDelay: `${i * 70}ms` }}
            >
              <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl border border-brand-500/25 bg-brand-500/10 text-brand-600 dark:text-brand-400">
                {f.icon}
              </span>
              <h3 className="mt-4">{f.title}</h3>
              <p className="mt-2 text-sm text-fg-muted">{f.desc}</p>
            </article>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="border-y border-ink-700 bg-ink-900/50">
        <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20">
          <h2>How it works</h2>
          <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <div key={s.step} className="animate-fade-in-up" style={{ animationDelay: `${i * 70}ms` }}>
                <div className="font-mono text-sm font-bold text-brand-600 dark:text-brand-400">{s.step}</div>
                <h3 className="mt-3">{s.title}</h3>
                <p className="mt-2 text-sm text-fg-muted">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-7xl px-4 py-20 sm:px-6">
        <div className="card relative overflow-hidden p-8 text-center sm:p-14">
          <div className="pointer-events-none absolute -left-24 -top-24 h-64 w-64 rounded-full bg-brand-500/15 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-24 -right-24 h-64 w-64 rounded-full bg-teal/10 blur-3xl" />
          <h2 className="relative">Ready to prove what you know?</h2>
          <p className="relative mx-auto mt-3 max-w-xl text-fg-muted">
            Join Survival School, climb the leaderboard, and earn certificates that hold up to scrutiny.
          </p>
          <div className="relative mt-8 flex flex-col justify-center gap-3 sm:flex-row">
            <Link href="/register" className="btn-primary !px-6 !py-3 text-base">
              Create your account <IconArrow />
            </Link>
            <Link href="/leaderboard" className="btn-secondary !px-6 !py-3 text-base">
              See the leaderboard
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}

/* Inline SVG icons (no emoji) */
function IconArrow() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}
function IconCheck() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} className="h-3.5 w-3.5 text-teal" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M20 6 9 17l-5-5" />
    </svg>
  );
}
function IconBook() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-6 w-6" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5zM4 20.5A2.5 2.5 0 0 0 6.5 23H20" />
    </svg>
  );
}
function IconBolt() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-6 w-6" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 2 4 14h7l-1 8 9-12h-7z" />
    </svg>
  );
}
function IconTrophy() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-6 w-6" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 21h8m-4-4v4m7-17H5v3a5 5 0 0 0 5 5h4a5 5 0 0 0 5-5zM5 4H3v2a3 3 0 0 0 3 3m13-5h2v2a3 3 0 0 1-3 3" />
    </svg>
  );
}
function IconSeal() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-6 w-6" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 2l2.6 1.6 3-.3 1.2 2.8 2.5 1.7-.9 2.9.9 2.9-2.5 1.7-1.2 2.8-3-.3L12 22l-2.6-1.6-3 .3-1.2-2.8L2.7 16l.9-2.9-.9-2.9 2.5-1.7L6.4 3.3l3 .3z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="m9 12 2 2 4-4" />
    </svg>
  );
}
function IconShield() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-6 w-6" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="m9 12 2 2 4-4" />
    </svg>
  );
}
function IconCampus() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-6 w-6" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 21h18M5 21V8l7-4 7 4v13M9 21v-5h6v5M9 11h.01M15 11h.01" />
    </svg>
  );
}
