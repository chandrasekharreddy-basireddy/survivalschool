"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { ThemeToggle } from "@/components/ThemeToggle";
import { SearchBar } from "@/components/SearchBar";
import { hasRole, isAdmin, isInstructor } from "@/lib/roles";

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

export function NavBar() {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const closeMobile = () => setMobileOpen(false);
  const canTeach = isInstructor(user);
  const canAdmin = isAdmin(user);
  const isPrivileged = hasRole(user, ["ADMIN", "SUPER_ADMIN", "INSTRUCTOR", "MODERATOR", "SUPPORT"]);

  const links = [
    ["/courses", "Courses", true],
    ["/contests", "Contests", true],
    ["/dashboard", "Dashboard", !!user],
    ["/timetable", "Timetable", !!user],
    ["/practice", "Practice", !!user],
    ["/leaderboard", "Ranks", !!user],
    ["/chat", "Chat", !!user],
    ["/ai-practice", "AI Practice", !!user],
    ["/ai-assistant", "AI Tutor", !!user],
    ["/instructor/courses", "Instructor", canTeach],
    ["/admin", "Admin", canAdmin],
  ] as const;

  const isActive = (href: string) => pathname === href || (href !== "/" && pathname.startsWith(href + "/"));
  const linkClass = (href: string) =>
    `rounded-lg px-2.5 py-1.5 text-[0.82rem] font-medium transition-colors ${
      isActive(href) ? "bg-ink-800 text-fg" : "text-fg-muted hover:bg-ink-800/70 hover:text-fg"
    }`;

  return (
    <header className="sticky top-0 z-40 border-b border-ink-700/80 bg-ink-950">
      <nav className="mx-auto flex min-h-14 max-w-7xl items-center gap-2 px-3 sm:px-5 lg:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-2.5 text-sm font-bold tracking-tight text-fg">
          <LogoMark />
          <span className="hidden text-[0.9rem] tracking-tight sm:inline">
            Survival<span className="text-brand-600 dark:text-brand-400"> School</span>
          </span>
        </Link>
        <div className="mx-auto hidden w-full max-w-sm md:block"><SearchBar /></div>
        <div className="ml-auto hidden items-center gap-0.5 lg:flex">
          {links.map(([href, label, visible]) => visible ? <Link key={href} href={href} className={linkClass(href)}>{label}</Link> : null)}
        </div>
        <div className="ml-auto flex items-center gap-1.5 lg:ml-2">
          <ThemeToggle />
          {loading ? null : user ? (
            <>
              <Link href="/notifications" className="hidden rounded-lg p-2 text-fg-muted hover:bg-ink-900 hover:text-fg sm:inline-flex" aria-label="Notifications"><BellIcon /></Link>
              <Link href="/profile" className="hidden max-w-28 truncate rounded-md px-2 py-1.5 text-xs font-medium text-fg-muted hover:bg-ink-900/80 hover:text-fg lg:inline" title={user.full_name}>{user.full_name}</Link>
              <button onClick={logout} className="btn-secondary hidden !min-h-9 !px-3 !py-1.5 sm:inline-flex">Sign out</button>
            </>
          ) : (
            <><Link href="/login" className="btn-secondary hidden !min-h-9 !px-3 !py-1.5 sm:inline-flex">Sign in</Link><Link href="/register" className="btn-primary !min-h-9 !px-3 !py-1.5">Join</Link></>
          )}
          <button onClick={() => setMobileOpen((value) => !value)} className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-ink-700 bg-ink-900 text-fg-muted hover:text-fg lg:hidden" aria-label="Toggle menu" aria-expanded={mobileOpen}><MenuIcon open={mobileOpen} /></button>
        </div>
      </nav>
      {mobileOpen && (
        <div className="border-t border-ink-700 bg-ink-950 px-3 py-3 sm:px-5 lg:hidden">
          <div className="mb-3"><SearchBar /></div>
          <div className="grid grid-cols-2 gap-1 text-sm text-fg-muted">
            {links.map(([href, label, visible]) => visible ? <Link key={href} href={href} onClick={closeMobile} className={linkClass(href)}>{label}</Link> : null)}
            {isPrivileged && <Link href="/notifications" onClick={closeMobile} className={linkClass("/notifications")}>Notifications</Link>}
            {user && <Link href="/profile" onClick={closeMobile} className={linkClass("/profile")}>{user.full_name}</Link>}
            {user ? <button onClick={() => { logout(); closeMobile(); }} className="btn-secondary col-span-2 mt-1">Sign out</button> : <Link href="/login" onClick={closeMobile} className="btn-secondary col-span-2 mt-1">Sign in</Link>}
          </div>
        </div>
      )}
    </header>
  );
}

function BellIcon() { return <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-5 w-5"><path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0" /></svg>; }
function MenuIcon({ open }: { open: boolean }) { return <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-5 w-5">{open ? <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" /> : <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M3.75 17.25h16.5" />}</svg>; }
