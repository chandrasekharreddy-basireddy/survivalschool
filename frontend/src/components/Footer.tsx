import Link from "next/link";

const LINK_GROUPS: { title: string; links: { href: string; label: string }[] }[] = [
  {
    title: "Platform",
    links: [
      { href: "/contests", label: "Contests" },
      { href: "/contests/ai-weekly/register", label: "AI Weekly Exam" },
      { href: "/elimination", label: "Elimination battles" },
      { href: "/leaderboard", label: "Leaderboard" },
      { href: "/certificates/verify", label: "Verify a certificate" },
    ],
  },
  {
    title: "Account",
    links: [
      { href: "/register", label: "Create an account" },
      { href: "/login", label: "Sign in" },
      { href: "/settings", label: "Settings" },
    ],
  },
  {
    title: "Legal",
    links: [
      { href: "/privacy", label: "Privacy" },
      { href: "/terms", label: "Terms" },
      { href: "/security", label: "Security" },
    ],
  },
];

function LogoMark() {
  return (
    <span className="relative inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-ink-700 bg-ink-900 shadow-sm">
      <svg viewBox="0 0 40 40" fill="none" className="h-6 w-6" aria-hidden="true">
        <circle cx="20" cy="21" r="14" stroke="rgb(var(--accent-2))" strokeWidth="2.4" />
        <path d="M20 8 32 30H8L20 8Z" fill="rgb(var(--brand))" />
        <rect x="15.5" y="21" width="9" height="9" rx="1.4" fill="#f4f6fb" />
      </svg>
    </span>
  );
}

/** Every group's links wrap on one flowing line instead of stacking as
 * full-width block rows — the old layout put 13 links one-per-row at a
 * 44px min-height each, ~940px of footer on a phone before you even
 * reached the copyright bar. */
export function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-ink-700">
      <div className="page-frame flex flex-col gap-6 py-8 sm:flex-row sm:items-start sm:justify-between sm:gap-12">
        <div className="shrink-0 sm:max-w-[260px]">
          <Link href="/" className="flex items-center gap-2.5">
            <LogoMark />
            <span className="text-sm font-bold tracking-tight text-fg">
              Survival<span className="text-brand-600 dark:text-brand-400"> School</span>
            </span>
          </Link>
          <p className="mt-2.5 text-sm text-fg-muted">
            A weekly AI exam, live elimination battles, and certificates you can verify.
          </p>
        </div>
        <div className="flex min-w-0 flex-col gap-3">
          {LINK_GROUPS.map((group) => (
            <div key={group.title} className="flex flex-wrap items-center gap-y-1">
              <span className="mr-3 shrink-0 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
                {group.title}
              </span>
              {group.links.map((l, i) => (
                <span key={l.href} className="flex items-center">
                  <Link
                    href={l.href}
                    className="rounded-lg px-2.5 py-2 text-sm text-fg-muted transition-colors hover:bg-ink-800 hover:text-fg"
                  >
                    {l.label}
                  </Link>
                  {i < group.links.length - 1 && (
                    <span className="hidden text-fg-subtle sm:inline" aria-hidden="true">&middot;</span>
                  )}
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="hairline">
        <div className="page-frame flex flex-col items-start justify-between gap-2 py-4 text-xs text-fg-subtle sm:flex-row sm:items-center">
          <p>&copy; {year} Survival School. All rights reserved.</p>
          <p>Built for universities. Every score is graded on the server.</p>
        </div>
      </div>
    </footer>
  );
}

export default Footer;
