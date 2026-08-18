import Link from "next/link";
import { HeroLivePanel } from "@/components/HeroLivePanel";

const STEPS = [
  { n: "1", title: "Register on Thursday", desc: "The enrolment window opens every Thursday (IST). Pick the courses your university offers and join." },
  { n: "2", title: "Work through the lessons", desc: "Each lesson ends in MCQ checkpoints, so you find out what stuck before the exam does." },
  { n: "3", title: "Sit the weekend exam", desc: "A fresh, AI-set paper runs Saturday and Sunday. It's fullscreen, proctored, and timed by the server." },
  { n: "4", title: "Earn a certificate", desc: "Finish in the top three and a certificate is issued to you, each with a public verification link." },
];

export default function LandingPage() {
  return (
    <div>
      {/* Hero */}
      <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6 sm:py-20">
        <div className="grid items-center gap-10 lg:grid-cols-[1.15fr_0.85fr]">
          <div>
            <p className="text-sm font-medium text-fg-subtle">A learning platform for universities</p>
            <h1 className="mt-3 max-w-xl">
              Courses, weekend exams, and certificates you can actually verify.
            </h1>
            <p className="mt-5 max-w-xl text-[1.05rem] leading-relaxed text-fg-muted">
              Survival School runs MCQ courses and proctored, AI-set exams every Saturday and Sunday. Every answer is
              graded on the server, and the weekend&rsquo;s top scorers earn a certificate with a public verification link.
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <Link href="/register" className="btn-primary sm:w-auto">Create an account</Link>
              <Link href="/courses" className="btn-secondary sm:w-auto">Browse courses</Link>
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
              Four steps, the same every week. The schedule and the scoring are fixed, so there are no surprises on exam day.
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
              <Point>Enrol in your university&rsquo;s courses and follow the timetable.</Point>
              <Point>Practise with quizzes, then sit the graded weekend exams.</Point>
              <Point>Track your rank, streak, and badges on the leaderboard.</Point>
              <Point>Collect certificates that anyone can verify from a link.</Point>
            </ul>
          </div>
          <div>
            <h2>For instructors</h2>
            <ul className="mt-4 space-y-3 text-fg-muted">
              <Point>Build courses and lessons, and manage a question bank.</Point>
              <Point>Let the platform set and run the weekend exams for you.</Point>
              <Point>Review flagged attempts from the integrity monitor.</Point>
              <Point>See who passed and let certificates issue automatically.</Point>
            </ul>
          </div>
        </div>
      </section>

      {/* Close */}
      <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6">
        <div className="flex flex-col items-start justify-between gap-6 rounded-lg border border-ink-700 bg-ink-900/40 p-8 sm:flex-row sm:items-center">
          <div>
            <h2 className="!text-xl">Enrolment opens Thursdays.</h2>
            <p className="mt-1 text-fg-muted">Create your account now so you&rsquo;re ready when the window opens.</p>
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
