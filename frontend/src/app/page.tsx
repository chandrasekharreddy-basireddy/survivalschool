import Link from "next/link";
import { HeroLivePanel } from "@/components/HeroLivePanel";

const STEPS = [
  { n: "1", title: "Create an account", desc: "Signup is open every day — no waiting for a window." },
  { n: "2", title: "Register for the weekly exam", desc: "Pick a subject and topic. Registration opens every Thursday (IST); the topic must clear a 70% AI difficulty bar." },
  { n: "3", title: "Sit the full 2-hour exam", desc: "50 questions, everyone completes the whole thing — no elimination. It's fullscreen, integrity-monitored, and graded entirely on the server." },
  { n: "4", title: "Or battle friends live", desc: "Host an elimination battle, invite people by name, and answer one question at a time under a strict 15-second clock. Miss it or get it wrong and you're out." },
];

export default function LandingPage() {
  return (
    <div>
      {/* Hero */}
      <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6 sm:py-20">
        <div className="grid items-center gap-10 lg:grid-cols-[1.15fr_0.85fr]">
          <div>
            <p className="text-sm font-medium text-fg-subtle">A competitive quiz platform for universities</p>
            <h1 className="mt-3 max-w-xl">
              A weekly AI exam, live elimination battles, and certificates you can actually verify.
            </h1>
            <p className="mt-5 max-w-xl text-[1.05rem] leading-relaxed text-fg-muted">
              Register for the AI Weekly Exam every Thursday, or start an elimination battle and invite your
              friends for a live, sudden-death quiz. Every answer is graded on the server, and top finishers earn
              a certificate with a public verification link.
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <Link href="/register" className="btn-primary sm:w-auto">Create an account</Link>
              <Link href="/contests" className="btn-secondary sm:w-auto">Browse contests</Link>
            </div>
          </div>

          <div className="lg:pl-4">
            <HeroLivePanel />
          </div>
        </div>
      </section>

      <div className="hairline mx-auto max-w-7xl" />

      {/* How it works — a plain numbered sequence, not a grid of identical cards */}
      <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6 sm:py-16">
        <div className="grid gap-10 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <h2>How it works</h2>
            <p className="mt-3 max-w-sm text-fg-muted">
              Two ways to compete: a fixed weekly exam everyone sits in full, or a live sudden-death battle you run
              with friends whenever you want.
            </p>
          </div>
          <ol className="space-y-6">
            {STEPS.map((s) => (
              <li key={s.n} className="flex gap-4">
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-ink-700 text-sm font-semibold text-fg-muted">
                  {s.n}
                </span>
                <div>
                  <h3>{s.title}</h3>
                  <p className="mt-1 max-w-lg text-sm text-fg-muted">{s.desc}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Two audiences, two different jobs */}
      <section className="border-t border-ink-700 bg-ink-900/40">
        <div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:grid-cols-2 sm:px-6 sm:py-16">
          <div>
            <h2>For students</h2>
            <ul className="mt-4 space-y-3 text-fg-muted">
              <Point>Register for the AI Weekly Exam every Thursday and sit the full 2-hour paper.</Point>
              <Point>Host or join elimination battles with friends — one wrong answer and you&rsquo;re out.</Point>
              <Point>Practise with bookmarks and past mistakes, untimed and low-stakes.</Point>
              <Point>Track your rank, streak, and badges — and collect verifiable certificates.</Point>
            </ul>
          </div>
          <div>
            <h2>For instructors</h2>
            <ul className="mt-4 space-y-3 text-fg-muted">
              <Point>Build and maintain the shared question bank by subject and topic.</Point>
              <Point>Bulk-import questions from CSV or XLSX.</Point>
              <Point>Review flagged attempts from the integrity monitor.</Point>
              <Point>Let the AI Weekly Exam generate and grade itself — certificates issue automatically.</Point>
            </ul>
          </div>
        </div>
      </section>

      {/* Close */}
      <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6">
        <div className="flex flex-col items-start justify-between gap-6 rounded-lg border border-ink-700 bg-ink-900/40 p-8 sm:flex-row sm:items-center">
          <div>
            <h2 className="!text-xl">AI Weekly Exam registration opens Thursdays.</h2>
            <p className="mt-1 text-fg-muted">Account signup is open every day, so you&rsquo;re ready whenever the window opens.</p>
          </div>
          <Link href="/register" className="btn-primary shrink-0 sm:w-auto">Create an account</Link>
        </div>
      </section>
    </div>
  );
}

function Point({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" aria-hidden="true" />
      <span>{children}</span>
    </li>
  );
}
