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

export function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-ink-700">
      <div className="page-frame grid gap-10 py-10 sm:grid-cols-2 lg:grid-cols-[1.3fr_1fr_1fr_1fr]">
        <div>
          <span className="text-sm font-semibold text-fg">Survival School</span>
          <p className="mt-2 max-w-xs text-sm text-fg-muted">
            A weekly AI exam, live elimination battles, and certificates you can verify.
          </p>
        </div>
        {LINK_GROUPS.map((group) => (
          <div key={group.title}>
            <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">{group.title}</p>
            {/* inline-flex + min-height keeps each link a comfortable tap
                target on touch screens; text-only links were ~17px tall. */}
            <ul className="mt-1 text-sm">
              {group.links.map((l) => (
                <li key={l.href}>
                  <Link
                    href={l.href}
                    className="inline-flex min-h-11 items-center text-fg-muted hover:text-fg"
                  >
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="hairline">
        <div className="page-frame flex flex-col items-start justify-between gap-2 py-5 text-xs text-fg-subtle sm:flex-row sm:items-center">
          <p>&copy; {year} Survival School. All rights reserved.</p>
          <p>Built for universities. Every score is graded on the server.</p>
        </div>
      </div>
    </footer>
  );
}

export default Footer;
