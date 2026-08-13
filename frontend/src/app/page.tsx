import Link from "next/link";

const FEATURES = [
  { title: "MCQ-first courses", desc: "Every lesson builds toward a real assessment — not passive video watching." },
  { title: "Timed exams that count", desc: "Server-authoritative timing and scoring. No client can fake a result." },
  { title: "Live leaderboards", desc: "Points, streaks, and badges — all computed server-side, all real." },
  { title: "Verifiable certificates", desc: "Every certificate has a public verification URL and QR code." },
  { title: "AI study assistant", desc: "Ask questions, get explanations, plan your study time — without spoiling answers." },
  { title: "Built for your university", desc: "Course catalogs, timetables, and cohorts that match how your campus actually runs." },
];

const STEPS = [
  { step: "01", title: "Enroll in a course", desc: "Browse the catalog and enroll in courses your university offers." },
  { step: "02", title: "Learn in short lessons", desc: "Work through bite-sized lessons designed around MCQ checkpoints." },
  { step: "03", title: "Prove it", desc: "Pass quizzes and timed exams, graded the moment you submit." },
  { step: "04", title: "Get certified", desc: "Earn a verifiable certificate the instant you finish a course." },
];

export default function LandingPage() {
  return (
    <div>
      <section className="relative overflow-hidden border-b border-ink-800">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-brand-900/40 via-ink-950 to-ink-950" />
        <div className="mx-auto max-w-6xl px-6 py-24 sm:py-32">
          <div className="max-w-2xl">
            <span className="inline-block rounded-full border border-brand-500/30 bg-brand-500/10 px-3 py-1 text-xs font-medium text-brand-400">
              Built for universities
            </span>
            <h1 className="mt-6 text-4xl font-bold tracking-tight text-white sm:text-6xl">
              Learning that feels like a game.
              <span className="block text-brand-400">Assessment that means something.</span>
            </h1>
            <p className="mt-6 text-lg text-slate-400">
              Survival School turns your course material into MCQ-driven lessons, timed exams, and a
              real leaderboard — with certificates your students can actually verify.
            </p>
            <div className="mt-10 flex flex-wrap gap-4">
              <Link href="/register" className="btn-primary !px-6 !py-3 text-base">Start learning free</Link>
              <Link href="/courses" className="btn-secondary !px-6 !py-3 text-base">Browse courses</Link>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="text-2xl font-bold text-white sm:text-3xl">Everything a modern EdTech platform needs</h2>
        <p className="mt-2 max-w-xl text-slate-400">No filler dashboards. No fake stats. Every number on this platform is computed by the backend.</p>
        <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="card">
              <h3 className="font-semibold text-white">{f.title}</h3>
              <p className="mt-2 text-sm text-slate-400">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="border-y border-ink-800 bg-ink-900/40">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <h2 className="text-2xl font-bold text-white sm:text-3xl">How it works</h2>
          <div className="mt-10 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s) => (
              <div key={s.step}>
                <div className="text-sm font-mono text-brand-400">{s.step}</div>
                <h3 className="mt-2 font-semibold text-white">{s.title}</h3>
                <p className="mt-1 text-sm text-slate-400">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-20">
        <div className="card flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
          <div>
            <h2 className="text-xl font-bold text-white">Have a certificate to check?</h2>
            <p className="mt-1 text-sm text-slate-400">Verify any Survival School certificate publicly — no account needed.</p>
          </div>
          <Link href="/certificates/verify" className="btn-secondary">Verify a certificate</Link>
        </div>
      </section>

      <footer className="border-t border-ink-800 py-10 text-center text-sm text-slate-500">
        Survival School — built for universities, not for demos.
      </footer>
    </div>
  );
}
